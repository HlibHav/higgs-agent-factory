"""Live session service: one browser microphone against one Higgs Realtime session.

`run_live` pumps microphone PCM into the session and session events out to a `LiveSink`,
until the first of: the live-session limit, the session ending, or the microphone ending.
It always closes the session and reports one `LiveEnd` to the sink. It reads no env and
imports no web framework: the sink is whatever the entry layer provides.

Boson facts: audio is 24 kHz s16le mono (F4); TTFA starts at the client's receipt of
`input_audio_buffer.speech_stopped` (F15) and ends at the first `response.output_audio.delta`
of the response that follows (F17); barge-in always interrupts (F8), so after
`speech_started` every response that was running is cancelled and its late deltas are
dropped; `session.idle_timeout` (F8) and close code 4429 (F13) arrive as `SessionEnded`.
"""

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from factory.agent_spec.models import AgentSpec, ClientTool
from factory.gate.runner import select_mock
from factory.ports import (
    AudioDelta,
    Clock,
    RealtimeSession,
    ResponseCreated,
    ResponseDone,
    SessionEnded,
    SessionEvent,
    SessionRefused,
    SpeechStarted,
    SpeechStopped,
    ToolCall,
    TranscriptDelta,
)

LIVE_TTFA_LABEL = "speech_stopped to first audio delta"  # F15, F17 (AC-41)
LIMIT_POLL_S = 0.25
CLOSE_TIMEOUT_S = 5.0
TRANSCRIPT_MAX_CHARS = 4000
REFUSED_TEXT_MAX_CHARS = 300

EndReason = Literal["limit reached", "inactivity", "quota refused", "closed", "error"]
Sleep = Callable[[float], Awaitable[None]]

_QUOTA_CODE = re.compile(r"\bcode 4429\b")  # F13: a close before session.created shows as text


@dataclass(frozen=True)
class LiveAudioDelta(AudioDelta):
    """An `AudioDelta` that also carries the decoded PCM, for playback in the browser."""

    pcm: bytes = b""


@dataclass(frozen=True)
class LiveEnd:
    reason: EndReason
    message: str


class LiveSink(Protocol):
    async def opened(self) -> None: ...

    async def audio(self, pcm: bytes) -> None: ...

    async def stop_playback(self, response_id: str | None) -> None:
        """Barge-in: the page must stop everything queued or playing at once (AC-42)."""
        ...

    async def ttfa(self, ms: float, label: str) -> None: ...

    async def transcript(self, text: str) -> None: ...

    async def ended(self, reason: EndReason, message: str) -> None: ...


def _limit_message(limit_s: float) -> str:
    return f"The live session limit of {limit_s:g} s was reached."


_INACTIVITY = LiveEnd("inactivity", "The session ended for inactivity.")
_QUOTA = LiveEnd("quota refused", "The API quota was refused; the session was not restarted.")
_CLOSED = LiveEnd("closed", "The session was closed.")
_CONCURRENCY = LiveEnd("error", "Too many live sessions are open at the provider; try again later.")


def _end_for(event: SessionEnded) -> LiveEnd:
    if event.cause == "quota refused":
        return _QUOTA
    if event.cause == "idle timeout":
        return _INACTIVITY
    if event.cause == "concurrency limit":
        return _CONCURRENCY
    return _CLOSED


def _refused_end(exc: SessionRefused) -> LiveEnd:
    if _QUOTA_CODE.search(exc.error_text):
        return _QUOTA
    return LiveEnd("error", f"The session was refused: {exc.error_text[:REFUSED_TEXT_MAX_CHARS]}")


class _Turns:
    """Event bookkeeping for one live session: TTFA, barge-in and the assistant transcript."""

    def __init__(self, spec: AgentSpec, session: RealtimeSession, out: LiveSink) -> None:
        self._session = session
        self._out = out
        self._tools = {t.name: t for t in spec.tools if isinstance(t, ClientTool)}
        self._stopped_t: float | None = None
        self._active: set[str] = set()
        self._cancelled: set[str] = set()
        self._texts: dict[str, list[str]] = {}
        self._ttfa_for: set[str] = set()

    async def handle(self, event: SessionEvent) -> LiveEnd | None:
        if isinstance(event, SessionEnded):
            return _end_for(event)
        if isinstance(event, SpeechStopped):
            self._stopped_t = event.t  # F15
        elif isinstance(event, SpeechStarted):
            self._stopped_t = None
            self._cancelled |= self._active  # F8: barge-in cancels what was running
            self._texts.clear()
            await self._out.stop_playback(next(iter(sorted(self._active)), None))
        elif isinstance(event, ResponseCreated):
            self._active.add(event.response_id)
        elif isinstance(event, AudioDelta):
            await self._on_audio(event)
        elif isinstance(event, TranscriptDelta):
            if event.response_id not in self._cancelled:
                self._texts.setdefault(event.response_id, []).append(event.text)  # F18
        elif isinstance(event, ResponseDone):
            await self._on_done(event)
        elif isinstance(event, ToolCall):
            await self._on_tool(event)
        return None

    async def _on_audio(self, event: AudioDelta) -> None:
        rid = event.response_id
        if rid in self._cancelled:
            return
        self._active.add(rid)
        if self._stopped_t is not None and rid not in self._ttfa_for:
            self._ttfa_for.add(rid)
            ms = max(0.0, (event.t - self._stopped_t) * 1000.0)
            self._stopped_t = None
            await self._out.ttfa(ms, LIVE_TTFA_LABEL)
        if isinstance(event, LiveAudioDelta) and event.pcm:
            await self._out.audio(event.pcm)

    async def _on_done(self, event: ResponseDone) -> None:
        rid = event.response_id
        self._active.discard(rid)
        parts = self._texts.pop(rid, [])
        if rid in self._cancelled:
            self._cancelled.discard(rid)
            return
        text = "".join(parts).strip()
        if text:
            await self._out.transcript(text[:TRANSCRIPT_MAX_CHARS])

    async def _on_tool(self, event: ToolCall) -> None:
        tool = self._tools.get(event.name)
        if event.executor == "client" and tool is not None:  # F10: the spec's own mock answers
            await self._session.send_tool_output(event.call_id, select_mock(tool, event.arguments))


async def _pump_mic(mic: AsyncIterator[bytes], session: RealtimeSession) -> LiveEnd:
    async for pcm in mic:
        await session.send_audio(pcm)
    return _CLOSED


async def _pump_events(events: AsyncIterator[SessionEvent], turns: _Turns) -> LiveEnd:
    async for event in events:
        end = await turns.handle(event)
        if end is not None:
            return end
    return _CLOSED


async def _watch_limit(limit_s: float, clock: Clock, sleep: Sleep) -> LiveEnd:
    deadline = clock() + limit_s
    while (remaining := deadline - clock()) > 0:
        await sleep(min(LIMIT_POLL_S, remaining))
    return LiveEnd("limit reached", _limit_message(limit_s))


async def _close_quietly(session: RealtimeSession) -> None:
    """Close the session even while this task is being cancelled (a client that left, a server
    shutdown). The close runs as its own task and is awaited for at most CLOSE_TIMEOUT_S; a
    cancellation that arrives meanwhile is re-raised once the close is done."""
    closing = asyncio.ensure_future(session.close())
    cancelled = False
    deadline = asyncio.get_running_loop().time() + CLOSE_TIMEOUT_S
    while not closing.done() and (left := deadline - asyncio.get_running_loop().time()) > 0:
        try:
            await asyncio.wait({closing}, timeout=left)
        except asyncio.CancelledError:
            cancelled = True
    if closing.done() and not closing.cancelled():
        closing.exception()  # a failing close is ignored, but its error is marked retrieved
    else:
        closing.cancel()
    if cancelled:
        raise asyncio.CancelledError


def _error_end(exc: BaseException) -> LiveEnd:
    return LiveEnd("error", f"The live session failed ({type(exc).__name__}).")


async def run_live(
    spec: AgentSpec,
    session: RealtimeSession,
    mic: AsyncIterator[bytes],
    out: LiveSink,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> LiveEnd:
    """Open the session, run until the first end condition, close it, tell the sink why."""
    end: LiveEnd | None = None
    tasks: list[asyncio.Task[LiveEnd]] = []
    try:
        try:
            await session.open(spec)
        except SessionRefused as exc:
            end = _refused_end(exc)
        except Exception as exc:  # noqa: BLE001 - reported to the user as a generic error
            end = _error_end(exc)
        if end is None:
            await out.opened()
            turns = _Turns(spec, session, out)
            # Order matters: when several finish together, the first listed decides the end.
            tasks = [
                asyncio.ensure_future(_pump_events(session.events(), turns)),
                asyncio.ensure_future(_watch_limit(spec.budget.max_live_session_s, clock, sleep)),
                asyncio.ensure_future(_pump_mic(mic, session)),
            ]
            end = await _first_end(tasks)
    finally:
        for task in tasks:
            task.cancel()
        await _close_quietly(session)  # first: it must run even if we are being cancelled
        await asyncio.gather(*tasks, return_exceptions=True)
    assert end is not None
    await out.ended(end.reason, end.message)
    return end


async def _first_end(tasks: list[asyncio.Task[LiveEnd]]) -> LiveEnd:
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    # `tasks` is ordered by priority: the session's own verdict (a quota close, an idle
    # timeout) beats the limit, which beats the microphone ending.
    for task in tasks:
        if task in done:
            exc = task.exception()
            return _error_end(exc) if exc is not None else task.result()
    raise AssertionError("asyncio.wait returned no finished task")
