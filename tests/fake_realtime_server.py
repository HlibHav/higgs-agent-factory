"""A scripted fake Boson Realtime server on localhost (no network beyond loopback).

Event shapes follow docs/boson-protocol.md only. `session_created` and `response_done` copy
results/smoke-20261024T145225Z.jsonl (VERIFIED-RUN, F1/F2/F14); audio, transcript and VAD
events follow the documented field lists (F15, F17, F18, VERIFIED-DOCS). The shape of the
`error` event (F13) is not recorded there, so no helper builds one: scripts pass raw dicts.

Script actions: `send(event)`, `wait_for(client_event_type)`, `delay(ms)`, `close(code)`.
F1/F14: nothing is sent until the first `session.update`, which is acked with
`session.created` (disable with `auto_ack=False`).
"""

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed


@dataclass(frozen=True)
class Received:
    event: dict[str, Any]
    t: float  # time.monotonic() on receipt
    conn: int = 0  # index of the connection that sent it


@dataclass(frozen=True)
class _Send:
    event: dict[str, Any]


@dataclass(frozen=True)
class _WaitFor:
    event_type: str


@dataclass(frozen=True)
class _Delay:
    ms: float


@dataclass(frozen=True)
class _Close:
    code: int


def send(event: dict[str, Any]) -> _Send:
    return _Send(event)


def wait_for(event_type: str) -> _WaitFor:
    return _WaitFor(event_type)


def delay(ms: float) -> _Delay:
    return _Delay(ms)


def close(code: int) -> _Close:
    return _Close(code)


Action = _Send | _WaitFor | _Delay | _Close


def session_created_event(*, voice: str = "default") -> dict[str, Any]:
    """F1, F14: shape of the smoke run's `session.created` (audio output configured)."""
    return {
        "event_id": "fake-session-created",
        "type": "session.created",
        "session": {
            "id": "fake0001",
            "type": "realtime",
            "object": "realtime.session",
            "audio": {
                "input": {
                    "format": {"rate": 24000, "type": "audio/pcm"},
                    "turn_detection": None,
                },
                "output": {"format": {"rate": 24000, "type": "audio/pcm"}, "voice": voice},
            },
            "model": "higgs-realtime",
            "output_modalities": ["audio"],
            "tools": [],
            "tool_choice": "auto",
            "truncation": "auto",
            "temperature": 0.3,
        },
    }


def audio_delta_event(response_id: str, nbytes: int = 4800) -> dict[str, Any]:
    """F17: `response.output_audio.delta` with base64 PCM (24 kHz s16le, F4)."""
    return {
        "event_id": f"fake-delta-{response_id}",
        "type": "response.output_audio.delta",
        "response_id": response_id,
        "item_id": "fake-item",
        "output_index": 0,
        "content_index": 0,
        "delta": base64.b64encode(b"\x00" * nbytes).decode(),
    }


def transcript_delta_event(response_id: str, text: str) -> dict[str, Any]:
    """F18: `response.output_audio_transcript.delta`."""
    return {
        "event_id": f"fake-transcript-{response_id}",
        "type": "response.output_audio_transcript.delta",
        "response_id": response_id,
        "item_id": "fake-item",
        "output_index": 0,
        "content_index": 0,
        "delta": text,
    }


def response_done_event(
    response_id: str,
    status: str = "completed",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """F2, F17: `response.done`; `usage` shape as observed in the smoke run, or None (docs)."""
    return {
        "event_id": f"fake-done-{response_id}",
        "type": "response.done",
        "response": {
            "id": response_id,
            "object": "realtime.response",
            "status": status,
            "status_details": None,
            "output": [],
            "usage": usage,
            "metadata": None,
        },
    }


def usage_dict(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> dict[str, Any]:
    """F2: the `usage` object as observed on the wire."""
    return {
        "total_tokens": input_tokens + output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_token_details": {"cached_tokens": cached_tokens},
    }


def speech_started_event(audio_start_ms: int = 0) -> dict[str, Any]:
    """F15."""
    return {
        "event_id": "fake-speech-started",
        "type": "input_audio_buffer.speech_started",
        "item_id": "fake-user-item",
        "audio_start_ms": audio_start_ms,
    }


def speech_stopped_event(audio_end_ms: int = 0) -> dict[str, Any]:
    """F15."""
    return {
        "event_id": "fake-speech-stopped",
        "type": "input_audio_buffer.speech_stopped",
        "item_id": "fake-user-item",
        "audio_end_ms": audio_end_ms,
    }


def idle_timeout_event() -> dict[str, Any]:
    """F8: sent after 5 minutes without detected user speech; the server then closes."""
    return {"event_id": "fake-idle", "type": "session.idle_timeout"}


@asynccontextmanager
async def fake_realtime_server(
    script: list[Action] | None = None,
    *,
    scripts: list[list[Action]] | None = None,
    auto_ack: bool = True,
) -> AsyncIterator[tuple[str, list[Received]]]:
    received: list[Received] = []
    arrived = asyncio.Event()
    connections = 0

    async def handler(ws: ServerConnection) -> None:
        nonlocal connections
        conn = connections
        connections += 1
        actions = script or []
        if scripts is not None:
            actions = scripts[conn] if conn < len(scripts) else []
        mine: list[Received] = []
        acked = False

        async def reader() -> None:
            nonlocal acked
            try:
                async for raw in ws:
                    event = json.loads(raw)
                    item = Received(event, time.monotonic(), conn)
                    received.append(item)
                    mine.append(item)
                    arrived.set()
                    if auto_ack and not acked and event.get("type") == "session.update":
                        acked = True
                        await ws.send(json.dumps(session_created_event()))
            except ConnectionClosed:
                pass
            finally:
                arrived.set()

        reader_task = asyncio.create_task(reader())
        cursor = 0
        try:
            for action in actions:
                if isinstance(action, _Send):
                    await ws.send(json.dumps(action.event))
                elif isinstance(action, _Delay):
                    await asyncio.sleep(action.ms / 1000)
                elif isinstance(action, _Close):
                    await ws.close(action.code)
                    return
                else:
                    while True:
                        match = next(
                            (
                                i
                                for i in range(cursor, len(mine))
                                if mine[i].event.get("type") == action.event_type
                            ),
                            None,
                        )
                        if match is not None:
                            cursor = match + 1
                            break
                        if ws.protocol.state.name == "CLOSED":
                            return
                        arrived.clear()
                        await arrived.wait()
            await reader_task
        except ConnectionClosed:
            pass
        finally:
            reader_task.cancel()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}", received
