"""Doubles for the film recorder tests. Not imported by anything under `factory/film/`."""

import array
import math
from collections.abc import Awaitable, Callable, Sequence

from factory.ports import TtsError, TtsRateLimited

RATE = 24000


def sine_pcm(seconds: float, freq: float = 440.0, amplitude: float = 0.3) -> bytes:
    """Loud 24 kHz s16le mono PCM (about -10 dBFS): `FakeTts`'s default is near-silent."""
    n = int(RATE * seconds)
    samples = array.array(
        "h", (int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / RATE)) for i in range(n))
    )
    return samples.tobytes()


def silence_pcm(seconds: float) -> bytes:
    return b"\x00\x00" * int(RATE * seconds)


class CountingTts:
    """Returns a sine whose length is `seconds` for every request and counts the requests."""

    def __init__(self, seconds: float = 0.5, pcm_for: Callable[[str], bytes] | None = None) -> None:
        self.seconds = seconds
        self.pcm_for = pcm_for
        self.requests: list[tuple[str, str]] = []

    async def synthesise(self, text: str, voice: str) -> bytes:
        self.requests.append((text, voice))
        if self.pcm_for is not None:
            return self.pcm_for(text)
        return sine_pcm(self.seconds)


class RateLimitedTts(CountingTts):
    """Answers 429 `fail_times` times, then succeeds. `always_other` raises a plain `TtsError`."""

    def __init__(self, fail_times: int, seconds: float = 0.5) -> None:
        super().__init__(seconds)
        self.fail_times = fail_times

    async def synthesise(self, text: str, voice: str) -> bytes:
        self.requests.append((text, voice))
        if len(self.requests) <= self.fail_times:
            raise TtsRateLimited("TTS request refused with status 429")
        return sine_pcm(self.seconds)


class BrokenTts(CountingTts):
    async def synthesise(self, text: str, voice: str) -> bytes:
        self.requests.append((text, voice))
        raise TtsError("TTS request failed with status 500")


class SleepLog:
    """An awaitable `sleep` that records the waits and returns at once."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


# --- run doubles ---------------------------------------------------------------------------

import asyncio  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

from factory.film.line_data import LineData  # noqa: E402
from factory.film.page_port import (  # noqa: E402
    AssistantChunk,
    BannerShown,
    CallerPlayed,
    PageEvent,
    PlaybackStopped,
    Ready,
    RequestBlocked,
    SessionEndedShown,
    SpeechStartedSignal,
    TranscriptShown,
    TtfaShown,
)
from factory.film.stems import StemCache, StemManifest, make_stems  # noqa: E402

TTFA_LABEL = "speech_stopped to first audio delta"


def build_manifest(base: Path, lines: LineData, stem_seconds: float = 0.3) -> StemManifest:
    """Real stems (loud sines) in `base/stems`, durations next to them, and the manifest."""
    cache = StemCache(base / "stems", CountingTts(stem_seconds), "higgs-tts-3", SleepLog())
    return asyncio.run(make_stems(lines, "nora", "jake", cache, base / "stems"))


class FakeServer:
    """`ServerPort` double: answers the screenplay's pre-take values unless told otherwise."""

    def __init__(self, **overrides: object) -> None:
        from factory.film.run import EXPECTED, ST_AGENT

        self.latest: dict[str, str | None] = {
            ST_AGENT: EXPECTED.st_latest,
            EXPECTED.brief_agent: EXPECTED.brief_latest,
        }
        self.pair: tuple[str, str] | None = EXPECTED.coach
        self.error: Exception | None = None
        for key, value in overrides.items():
            setattr(self, key, value)
        self.reads: list[str] = []

    async def latest_run_id(self, agent_id: str) -> str | None:
        self.reads.append(f"latest:{agent_id}")
        if self.error is not None:
            raise self.error
        return self.latest.get(agent_id)

    async def coach_pair(self, agent_id: str) -> tuple[str, str] | None:
        self.reads.append(f"coach:{agent_id}")
        if self.error is not None:
            raise self.error
        return self.pair


@dataclass
class Scenario:
    """What the scripted page reports for one take. Times are seconds on the virtual clock."""

    released: bool | None = True
    reply_after_s: float | None = 0.8  # first T1-reply chunk, after T1 starts
    reply_len_s: float = 4.0
    signal_after_s: float | None = 0.2  # speech_started after T2 starts
    stops: bool = True
    t2_reply_len_s: float = 1.5
    transcript: str | None = "I can't share that. Let's go back to the policy."
    ended: tuple[float, str] | None = None  # (seconds after Start, reason)
    blocked: str | None = None  # a request label reported 0.1 s after ready
    on_start: Callable[[], None] | None = None


class Sim:
    """A virtual clock shared by the scripted pages. `sleep` advances it and delivers events."""

    def __init__(self, scenarios: list[Scenario] | None = None, avatar_ticked: bool = False):
        self.t = 0.0
        self.scenarios = list(scenarios or [Scenario()])
        self.avatar = avatar_ticked
        self.pages: list[ScriptedPage] = []
        self.active: ScriptedPage | None = None
        self.gate: asyncio.Event | None = None  # when set up, the first page waits for it
        self.waits: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.t += seconds
        if self.active is not None:
            self.active.flush(self.t)
        for _ in range(3):
            await asyncio.sleep(0)

    async def factory(self) -> "ScriptedPage":
        if self.gate is not None and not self.pages:
            await self.gate.wait()
        page = ScriptedPage(self)
        self.pages.append(page)
        self.active = page
        return page

    @property
    def started(self) -> int:
        return sum(1 for p in self.pages if p.started)

    def next_scenario(self) -> Scenario:
        index = min(self.started - 1, len(self.scenarios) - 1)
        return self.scenarios[index]


class ScriptedPage:
    """`PagePort` double that replays a `Scenario` in virtual time and keeps a call log."""

    def __init__(self, sim: Sim) -> None:
        self.sim = sim
        self.calls: list[str] = []
        self.video: Path | None = None
        self.started = False
        self.scenario = Scenario()
        self._queue: asyncio.Queue[PageEvent | None] = asyncio.Queue()
        self._pending: list[tuple[float, int, PageEvent]] = []
        self._seq = 0
        self._chunks: list[AssistantChunk] = []
        self._pcm_s: dict[str, float] = {}
        self.agent: str | None = None

    def _at(self, when: float, event: PageEvent) -> None:
        self._seq += 1
        self._pending.append((when, self._seq, event))

    def flush(self, now: float) -> None:
        due = sorted(p for p in self._pending if p[0] <= now)
        self._pending = [p for p in self._pending if p[0] > now]
        for _, _, event in due:
            self._queue.put_nowait(event)

    async def open(self, base_url: str, video_path: Path | None) -> None:
        self.calls.append("open")
        self.video = video_path

    async def select_agent(self, agent_id: str) -> None:
        self.calls.append(f"select:{agent_id}")
        self.agent = agent_id

    async def avatar_ticked(self) -> bool:
        return self.sim.avatar

    async def show(self, target: str) -> None:
        self.calls.append(f"show:{target}")

    async def boxes(self, locators: Sequence[str]) -> dict[str, tuple[float, float, float, float]]:
        return {loc: (10.0, 20.0, 300.0, 40.0) for loc in locators}

    async def sync_mark(self) -> float:
        self.calls.append("sync_mark")
        return self.sim.t

    async def load_caller(self, line_id: str, pcm: bytes) -> None:
        self._pcm_s[line_id] = len(pcm) / 2 / RATE

    async def begin_take(self) -> float:
        self.calls.append("begin_take")
        return self.sim.t

    async def click_start(self) -> None:
        self.calls.append("click_start")
        self.started = True
        sc = self.scenario = self.sim.next_scenario()
        if sc.on_start is not None:
            sc.on_start()
        ready_at = self.sim.t + 0.2
        self._at(ready_at, Ready(ready_at, sc.released))
        if sc.released is False:
            self._at(ready_at, BannerShown(ready_at))
        if sc.blocked is not None:
            self._at(ready_at + 0.1, RequestBlocked(ready_at + 0.1, sc.blocked))
        if sc.ended is not None:
            at = self.sim.t + sc.ended[0]
            self._at(at, SessionEndedShown(at, sc.ended[1], "scripted end"))

    async def play_caller(self, line_id: str, at: float | None) -> None:
        self.calls.append(f"play:{line_id}")
        sc = self.scenario
        when = self.sim.t if at is None else at
        duration = self._pcm_s[line_id]
        if line_id == "T1":
            self._at(when, CallerPlayed(when, "T1", duration))
            if sc.reply_after_s is not None:
                first = when + sc.reply_after_s
                chunk = AssistantChunk(first, first, first + sc.reply_len_s)
                self._chunks.append(chunk)
                self._at(first, TtfaShown(first, 800.0, TTFA_LABEL))
                self._at(first, chunk)
            return
        if not any(c.start <= when < c.end for c in self._chunks):
            return  # the page cancels T2 itself when no assistant source is playing (AC-20)
        self._at(when, CallerPlayed(when, "T2", duration))
        if sc.signal_after_s is not None:
            signal = when + sc.signal_after_s
            self._at(signal, SpeechStartedSignal(signal))
            if sc.stops:
                self._at(signal + 0.02, PlaybackStopped(signal + 0.02))
        recv = when + 0.5
        self._at(recv, TtfaShown(recv, 700.0, TTFA_LABEL))
        self._at(recv, AssistantChunk(recv, recv, recv + sc.t2_reply_len_s))
        if sc.transcript is not None:
            end = recv + sc.t2_reply_len_s
            self._at(end, TranscriptShown(end, sc.transcript))

    async def click_stop(self) -> None:
        self.calls.append("click_stop")

    async def click(self, selector: str) -> None:
        self.calls.append(f"click:{selector}")

    def events(self) -> AsyncIterator[PageEvent]:
        async def gen() -> AsyncIterator[PageEvent]:
            while True:
                item = await self._queue.get()
                if item is None:
                    return
                yield item

        return gen()

    async def end_take(self, path: Path) -> None:
        self.calls.append("end_take")
        path.write_bytes(b"webm")

    async def close(self) -> None:
        self.calls.append("close")
        self._queue.put_nowait(None)
        if self.sim.active is self:
            self.sim.active = None


# --- loopback page: a real demo server on 127.0.0.1 -----------------------------------------

import contextlib  # noqa: E402
import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

from factory.composition import FactoryApp  # noqa: E402
from factory.film.guard import blocked_label  # noqa: E402
from factory.live.session import LiveAudioDelta  # noqa: E402
from factory.ports import (  # noqa: E402
    ResponseCreated,
    ResponseDone,
    SpeechStarted,
    SpeechStopped,
    TranscriptDelta,
)
from factory.web.app import create_web_app  # noqa: E402
from tests.doubles import Delay, FakeJudge, FakeSessionFactory  # noqa: E402

# Clicks the product page can make, as the request each would send.
CLICKS = {
    "#gateBtn": ("POST", "/api/agents/specialist-training/gate"),
    "#coachBtn": ("POST", "/api/agents/specialist-training/coach/run"),
    "#checkBtn": ("POST", "/api/agents/specialist-training/scenarios/st-1/check"),
    "#briefBtn": ("POST", "/api/brief"),
    "#saveBtn": ("POST", "/api/proposals/p1/save"),
    "#avatarToggle": ("POST", "/api/avatar/session"),
}


class RequestLog:
    """Every request the demo server saw, in order: (kind, method, path)."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def count(self, method: str, path: str) -> int:
        return sum(1 for _, m, p in self.items if m == method and p == path)

    def websockets(self) -> list[tuple[str, str, str]]:
        return [i for i in self.items if i[0] == "websocket"]


class _Counting:
    def __init__(self, app: Any, log: RequestLog) -> None:
        self._app = app
        self._log = log

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket"):
            method = scope.get("method", "WS")
            self._log.items.append((scope["type"], method, scope["path"]))
        await self._app(scope, receive, send)


class _Store:
    def __init__(self, released: bool) -> None:
        self._card = SimpleNamespace(
            verdict="released" if released else "rejected",
            run_id="20261024T180110Z-b501e4a3",
            agent_spec=None,
            agent_version=1,
        )

    def latest(self, agent_id: str) -> Any:
        return self._card

    def save(self, card: Any) -> Path:  # pragma: no cover - the recorder never saves
        raise AssertionError("the recorder must never write a card")


def live_script(
    agent_s: float = 4.0, reply: str = "I can't share that. Back to the policy."
) -> Any:
    """The fake agent: a long reply to T1 about 1 s after the session opens, a barge-in at
    2.7 s (T2 starts at first audio + 1.5 s), then a short reply with its transcript."""
    agent = sine_pcm(agent_s, 220.0)
    answer = sine_pcm(1.0, 330.0)
    return [
        ResponseCreated("r1", 0.0),
        Delay(1.0),
        SpeechStopped(0.0),
        LiveAudioDelta("r1", len(agent), 0.8, pcm=agent),
        Delay(1.7),
        SpeechStarted(2.0),
        SpeechStopped(2.1),
        ResponseCreated("r2", 2.2),
        TranscriptDelta("r2", reply, 2.3),
        LiveAudioDelta("r2", len(answer), 2.8, pcm=answer),
        ResponseDone("r2", "completed", None, 2.9),
        Delay(60.0),
    ]


@contextlib.contextmanager
def loopback_server(
    tmp_path: Path, released: bool = True, script: Any = None
) -> Iterator[tuple[str, RequestLog]]:
    """The real demo web app on 127.0.0.1:0 with a scripted live session and a request log."""
    factory = FakeSessionFactory(live_script() if script is None else script)
    app = FactoryApp(
        sessions=FakeSessionFactory(),
        audio=SimpleNamespace(),  # type: ignore[arg-type]
        judge=FakeJudge([]),
        store=_Store(released),  # type: ignore[arg-type]
        live_sessions=factory,
    )
    log = RequestLog()
    config = uvicorn.Config(
        _Counting(create_web_app(app), log), host="127.0.0.1", port=0, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", log
    finally:
        server.should_exit = True
        thread.join(timeout=15)


class LoopbackPage:
    """`PagePort` over a real loopback server. HTTP goes through `blocked_label`, the live
    session over a real WebSocket, and the page's playhead is simulated. Real time (the page
    clock is `time.monotonic()`). `inject_click` makes the page issue a product click."""

    def __init__(self, inject_on_open: str | None = None) -> None:
        self.inject_on_open = inject_on_open
        self.started = False
        self.video: Path | None = None
        self._http: httpx.AsyncClient | None = None
        self._ws: Any = None
        self._queue: asyncio.Queue[PageEvent | None] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._chunks: list[AssistantChunk] = []
        self._playhead = 0.0
        self._pcm: dict[str, bytes] = {}
        self._base = ""

    def _emit(self, event: PageEvent) -> None:
        self._queue.put_nowait(event)

    async def _get(self, path: str) -> None:
        assert self._http is not None
        url = self._base + path
        assert blocked_label("GET", url) is None
        response = await self._http.get(path)
        # The saved brief agent is not in this app's store: a 404 there is fine, a 5xx is not.
        assert response.status_code < 500, (path, response.status_code)

    async def inject_click(self, selector: str) -> None:
        method, path = CLICKS[selector]
        label = blocked_label(method, self._base + path)
        if label is not None:
            self._emit(RequestBlocked(time.monotonic(), label))  # aborted, never sent
        else:  # pragma: no cover - every CLICKS entry is one of the six
            assert self._http is not None
            await self._http.request(method, path)

    async def open(self, base_url: str, video_path: Path | None) -> None:
        self._base = base_url
        self.video = video_path
        self._http = httpx.AsyncClient(base_url=base_url, timeout=10)
        await self._get("/")
        if self.inject_on_open:
            selector = self.inject_on_open

            async def later() -> None:
                await asyncio.sleep(0.01)
                await self.inject_click(selector)

            self._tasks.append(asyncio.create_task(later()))

    async def select_agent(self, agent_id: str) -> None:
        await self._get(f"/api/agents/{agent_id}/spec")

    async def avatar_ticked(self) -> bool:
        return False

    async def show(self, target: str) -> None:
        return None

    async def boxes(self, locators: Sequence[str]) -> dict[str, tuple[float, float, float, float]]:
        return {loc: (0.0, 0.0, 1.0, 1.0) for loc in locators}

    async def sync_mark(self) -> float:
        return time.monotonic()

    async def load_caller(self, line_id: str, pcm: bytes) -> None:
        self._pcm[line_id] = pcm

    async def begin_take(self) -> float:
        return time.monotonic()

    async def click_start(self) -> None:
        self.started = True
        ws_url = self._base.replace("http://", "ws://") + "/ws/live/specialist-training"
        self._ws = await connect(ws_url, max_size=None)
        self._tasks.append(asyncio.create_task(self._read()))

    async def _read(self) -> None:
        try:
            async for message in self._ws:
                now = time.monotonic()
                if isinstance(message, bytes):
                    start = max(now, self._playhead)
                    end = start + len(message) / 2 / RATE
                    self._playhead = end
                    chunk = AssistantChunk(now, start, end)
                    self._chunks.append(chunk)
                    self._emit(chunk)
                    continue
                m = json.loads(message)
                kind = m.get("type")
                if kind == "ready":
                    self._emit(Ready(now, m.get("released")))
                    if m.get("released") is False:
                        self._emit(BannerShown(now))
                elif kind in ("speech_started", "clear"):
                    self._playhead = now
                    self._emit(SpeechStartedSignal(now))
                    self._emit(PlaybackStopped(now))
                elif kind == "ttfa":
                    self._emit(TtfaShown(now, float(m["ms"]), str(m["label"])))
                elif kind == "transcript":
                    self._emit(TranscriptShown(now, str(m["text"])))
                elif kind == "ended":
                    self._emit(SessionEndedShown(now, str(m["reason"]), str(m["message"])))
        except Exception:  # noqa: BLE001 - the socket closed under us
            return

    async def play_caller(self, line_id: str, at: float | None) -> None:
        async def play() -> None:
            now = time.monotonic()
            when = now if at is None else at
            await asyncio.sleep(max(0.0, when - now))
            if line_id == "T2" and not any(c.start <= when < c.end for c in self._chunks):
                return  # AC-20: the page cancels T2 when nothing is playing
            pcm = self._pcm[line_id]
            self._emit(CallerPlayed(when, line_id, len(pcm) / 2 / RATE))  # type: ignore[arg-type]
            for i in range(0, len(pcm), 4800):
                await self._ws.send(pcm[i : i + 4800])

        self._tasks.append(asyncio.create_task(play()))

    async def click_stop(self) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def click(self, selector: str) -> None:
        await self.inject_click(selector)

    def events(self) -> AsyncIterator[PageEvent]:
        async def gen() -> AsyncIterator[PageEvent]:
            while True:
                item = await self._queue.get()
                if item is None:
                    return
                yield item

        return gen()

    async def end_take(self, path: Path) -> None:
        path.write_bytes(b"webm")

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._ws is not None:
            await self._ws.close()
        if self._http is not None:
            await self._http.aclose()
        self._queue.put_nowait(None)


def fast_sleep(real_polls: float = 0.2) -> Callable[[float], Awaitable[None]]:
    """Real polls (<= `real_polls` s) and holds shrunk to 2%: the film's long holds are for the
    video, not for the logic under test."""

    async def sleep(seconds: float) -> None:
        await asyncio.sleep(seconds if seconds <= real_polls else seconds * 0.02)

    return sleep
