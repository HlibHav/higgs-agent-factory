"""Demo web server (entry layer): the page, a few JSON routes and the live WebSocket.

Routes only parse input, call `FactoryApp` or `run_live`, and map the result. API keys live
in the composition root and never reach a response or a message (AC-37). The server is a
single-user local tool: it binds to 127.0.0.1 (see `factory.__main__`), refuses requests whose
Origin is another site, and runs at most one live session at a time.

Live WebSocket `WS /ws/live/{agent_id}`: binary frames in are 24 kHz s16le mono microphone
PCM, `{"type":"stop"}` ends the session. Out: JSON events (`ready`, `speech_started`, `ttfa`,
`transcript`, `ended`) and binary assistant PCM. One writer task owns every send; all queues
are bounded.
"""

import asyncio
import json
import time
from collections import deque
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from factory.agent_spec.generator import BriefTooLong, generate_from_brief
from factory.composition import CheckFailed, FactoryApp
from factory.gate.diff import diff_cards
from factory.gate.render import render_card_text
from factory.live.session import EndReason, LiveSink, Sleep, run_live
from factory.ports import Clock

DEFAULT_INDEX = Path(__file__).parent / "static" / "index.html"
MIC_QUEUE_FRAMES = 100  # mic frames are dropped, never queued without bound
MIC_FRAME_MAX_BYTES = 32_768  # about 680 ms; a page sends 40 to 100 ms
OUT_AUDIO_FRAMES = 100  # assistant audio waiting for the writer; the oldest is dropped
WRITER_DRAIN_TIMEOUT_S = 5.0
WS_POLICY_VIOLATION = 1008


def _origin_ok(headers: Mapping[str, str]) -> bool:
    """A page from another site must not drive this server: Origin, when sent, must be ours."""
    origin = headers.get("origin")
    if origin is None:
        return True  # not a browser page (curl, tests)
    return urlsplit(origin).netloc == headers.get("host", "")


class _Outbox:
    """Everything bound for the browser, in order. Audio is bounded; text is small and rare."""

    def __init__(self, max_audio: int = OUT_AUDIO_FRAMES) -> None:
        self._items: deque[bytes | str] = deque()
        self._audio = 0
        self._max_audio = max_audio
        self._wake = asyncio.Event()
        self._closed = False
        self._dead = False

    def put_text(self, text: str) -> None:
        if self._dead:
            return
        self._items.append(text)
        self._wake.set()

    def put_audio(self, pcm: bytes) -> None:
        if self._dead:
            return
        if self._audio >= self._max_audio:  # drop the oldest audio frame
            for i, item in enumerate(self._items):
                if isinstance(item, bytes):
                    del self._items[i]
                    self._audio -= 1
                    break
        self._items.append(pcm)
        self._audio += 1
        self._wake.set()

    def clear_audio(self) -> None:
        self._items = deque(i for i in self._items if isinstance(i, str))
        self._audio = 0

    def close(self) -> None:
        """No more input; the writer drains what is queued and stops."""
        self._closed = True
        self._wake.set()

    def kill(self) -> None:
        """The browser is gone: drop everything, accept nothing."""
        self._dead = True
        self._items.clear()
        self._audio = 0
        self._wake.set()

    async def get(self) -> bytes | str | None:
        while True:
            if self._items:
                item = self._items.popleft()
                if isinstance(item, bytes):
                    self._audio -= 1
                return item
            if self._closed or self._dead:
                return None
            self._wake.clear()
            await self._wake.wait()


class _Inbox:
    """Microphone frames from the browser: bounded, drops frames when the session is slower."""

    def __init__(self) -> None:
        self._q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MIC_QUEUE_FRAMES)

    def push(self, pcm: bytes) -> None:
        try:
            self._q.put_nowait(pcm)
        except asyncio.QueueFull:
            pass

    def end(self) -> None:
        if self._q.full():
            self._q.get_nowait()
        self._q.put_nowait(None)

    async def frames(self) -> AsyncIterator[bytes]:
        while (frame := await self._q.get()) is not None:
            yield frame


class _WsSink:
    """`LiveSink` that turns session callbacks into outbound frames."""

    def __init__(self, outbox: _Outbox, ready: dict[str, Any]) -> None:
        self._outbox = outbox
        self._ready = ready

    def _json(self, payload: dict[str, Any]) -> None:
        self._outbox.put_text(json.dumps(payload))

    async def opened(self) -> None:
        self._json({"type": "ready", **self._ready})

    async def audio(self, pcm: bytes) -> None:
        self._outbox.put_audio(pcm)

    async def stop_playback(self, response_id: str | None) -> None:
        self._outbox.clear_audio()
        self._json({"type": "speech_started"})

    async def ttfa(self, ms: float, label: str) -> None:
        self._json({"type": "ttfa", "ms": round(ms, 1), "label": label})

    async def transcript(self, text: str) -> None:
        self._json({"type": "transcript", "role": "assistant", "text": text})

    async def ended(self, reason: EndReason, message: str) -> None:
        self._json({"type": "ended", "reason": reason, "message": message})


async def _write(ws: WebSocket, outbox: _Outbox, inbox: _Inbox) -> None:
    """The only task that sends on the socket."""
    try:
        while (item := await outbox.get()) is not None:
            if isinstance(item, bytes):
                await ws.send_bytes(item)
            else:
                await ws.send_text(item)
    except Exception:  # noqa: BLE001 - browser gone (WebSocketDisconnect, RuntimeError, ...)
        outbox.kill()
        inbox.end()  # nobody can hear the session now: let run_live finish


async def _read(ws: WebSocket, inbox: _Inbox) -> None:
    """Browser to session: binary frames are microphone PCM, `{"type":"stop"}` ends it."""
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                data = data[: len(data) // 2 * 2]  # whole 16-bit samples only
                if data and len(data) <= MIC_FRAME_MAX_BYTES:
                    inbox.push(data)
                continue
            if _is_stop(message.get("text")):
                return
    except Exception:  # noqa: BLE001 - a broken socket is the same as a closed one
        return
    finally:
        inbox.end()


def _is_stop(text: str | None) -> bool:
    try:
        payload = json.loads(text or "")
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("type") == "stop"


def _card_json(card: Any) -> dict[str, Any]:
    """Card as JSON for the page; the spec snapshot is large and the page has its own view."""
    body: dict[str, Any] = json.loads(card.model_dump_json())
    body.pop("agent_spec", None)
    return body


def _plain_ended(reason: EndReason, message: str) -> str:
    return json.dumps({"type": "ended", "reason": reason, "message": message})


def create_web_app(
    factory_app: FactoryApp,
    *,
    index_path: Path = DEFAULT_INDEX,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await factory_app.aclose()

    app = FastAPI(title="Higgs Agent Factory", lifespan=lifespan, docs_url=None, redoc_url=None)
    live_running = False

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        if request.method not in ("GET", "HEAD") and not _origin_ok(request.headers):
            return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    async def page() -> Response:
        if not index_path.is_file():
            return PlainTextResponse("The demo page is not built yet.", status_code=404)
        return FileResponse(index_path, media_type="text/html")

    @app.get("/api/templates")
    async def templates() -> list[dict[str, Any]]:
        return [
            {
                "template_id": c.template_id,
                "name": c.name,
                "description": c.description,
                "source_url": c.source_url,
                "available": c.available,
            }
            for c in factory_app.list_templates()
        ]

    @app.get("/api/agents/{template_id}/spec")
    async def spec(template_id: str) -> dict[str, Any]:
        found = factory_app.agent_spec(template_id)
        if found is None:
            raise HTTPException(404, "unknown agent")
        return found.model_dump(mode="json")

    @app.get("/api/agents/{agent_id}/card/latest")
    async def latest_card(agent_id: str) -> dict[str, Any]:
        card = factory_app.latest_card(agent_id)
        if card is None:
            raise HTTPException(404, "no gate run yet")
        return {"card": _card_json(card), "text": render_card_text(card)}

    @app.get("/api/agents/{agent_id}/coach")
    async def coach(agent_id: str) -> dict[str, Any]:
        pair_fn = getattr(factory_app, "coach_pair", None)
        pair = pair_fn(agent_id) if pair_fn is not None else None
        if pair is None:
            raise HTTPException(404, "no coached version yet")
        before, after = pair
        return {
            "before": _card_json(before),
            "after": _card_json(after),
            "diff": diff_cards(before, after).model_dump(mode="json"),
        }

    @app.post("/api/brief")
    async def brief(payload: dict[str, Any]) -> Any:
        text = payload.get("brief")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(400, "The brief is empty.")
        if factory_app.brief_model is None:
            raise HTTPException(503, "No brief model is configured.")
        try:
            generated = await generate_from_brief(text, factory_app.brief_model)
        except BriefTooLong as exc:
            raise HTTPException(400, str(exc)) from None
        except Exception as exc:  # noqa: BLE001 - a model/API failure is a gateway error
            raise HTTPException(
                502, f"The brief model call failed ({type(exc).__name__})."
            ) from None
        if isinstance(generated, list):
            return JSONResponse(
                {"issues": [i.model_dump(mode="json") for i in generated]}, status_code=422
            )
        return generated.model_dump(mode="json")  # proposed, not gated: no gate run here (AC-79)

    @app.get("/api/agents/{agent_id}/scenarios")
    async def scenarios(agent_id: str) -> list[dict[str, str]]:
        found = factory_app.agent_spec(agent_id)
        if found is None:
            raise HTTPException(404, "unknown agent")
        return [{"scenario_id": s.id, "title": s.title} for s in found.scenarios]

    @app.post("/api/agents/{agent_id}/scenarios/{scenario_id}/check")
    async def check(agent_id: str, scenario_id: str) -> dict[str, Any]:
        try:
            result = await factory_app.run_single_scenario(agent_id, scenario_id)
        except KeyError:
            raise HTTPException(404, "unknown agent or scenario") from None
        except CheckFailed as exc:
            raise HTTPException(502, str(exc)) from None
        return {
            "scenario_id": result.scenario_id,
            "label": result.label,
            "rationale": result.rationale,
            "evidence": result.evidence,
            "ttfa_ms": result.ttfa_ms,
            "marker": "single-scenario check",
            "stored_verdict": result.stored_verdict,
        }

    @app.websocket("/ws/live/{agent_id}")
    async def live(ws: WebSocket, agent_id: str) -> None:
        nonlocal live_running
        if not _origin_ok(ws.headers):
            await ws.close(code=WS_POLICY_VIOLATION)
            return
        await ws.accept()
        found = factory_app.agent_spec(agent_id)
        if found is None or live_running:
            message = "Unknown agent." if found is None else "Another live session is running."
            await _reject(ws, _plain_ended("error", message))
            return
        live_running = True
        try:
            card = factory_app.latest_card(agent_id)
            ready = {
                "agent_id": agent_id,
                "released": card is not None and card.verdict == "released",
                "verdict": None if card is None else card.verdict,
                "run_id": None if card is None else card.run_id,
                "limit_s": int(found.budget.max_live_session_s),
            }
            await _serve(ws, found, ready, factory_app, clock, sleep)
        finally:
            live_running = False

    return app


async def _reject(ws: WebSocket, text: str) -> None:
    try:
        await ws.send_text(text)
        await ws.close()
    except Exception:  # noqa: BLE001 - the browser already left
        pass


async def _serve(
    ws: WebSocket,
    spec: Any,
    ready: dict[str, Any],
    factory_app: FactoryApp,
    clock: Clock,
    sleep: Sleep,
) -> None:
    outbox, inbox = _Outbox(), _Inbox()
    sink: LiveSink = _WsSink(outbox, ready)
    writer = asyncio.create_task(_write(ws, outbox, inbox))
    reader = asyncio.create_task(_read(ws, inbox))
    try:
        await run_live(spec, factory_app.new_live_session(), inbox.frames(), sink, clock, sleep)
    except Exception as exc:  # noqa: BLE001 - run_live reports its own ends; this is a bug net
        outbox.put_text(_plain_ended("error", f"The live session failed ({type(exc).__name__})."))
    finally:
        reader.cancel()
        outbox.close()
        await asyncio.gather(reader, return_exceptions=True)
        try:
            await asyncio.wait_for(writer, WRITER_DRAIN_TIMEOUT_S)
        except Exception:  # noqa: BLE001 - a stuck writer is cancelled, not waited for
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001 - already closed by the browser
            pass
