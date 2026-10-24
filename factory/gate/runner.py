"""Gate runner (service): preflight and the run loop. Receives ports, reads no env.

Boson facts used here: audio is 24 kHz s16le mono, 48,000 bytes per second (F4); a client
function tool call is answered with `send_tool_output` (F10, F15 via the session port);
unknown events are ignored (F5); a session that ends is reported as a `SessionEnded` cause
(F8 idle timeout, F13 quota 4429, F21 concurrency 1013).
"""

import asyncio
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from factory.agent_spec.models import (
    AgentSpec,
    BudgetLimits,
    ClientTool,
    ExpectedCall,
    Scenario,
)
from factory.agent_spec.validation import validate_agent_spec
from factory.gate.judge import judge_scenario
from factory.gate.playback import BYTES_PER_S, Sleep, play_turn, stream_silence_until, ttfa_ms
from factory.gate.records import (
    Cause,
    GateRunRecord,
    ScenarioRecord,
    TurnRecord,
)
from factory.gate.tts_cache import AudioMissing, TurnAudioSource
from factory.ports import (
    AudioDelta,
    Clock,
    JudgePort,
    JudgeRequest,
    RealtimeSession,
    ResponseDone,
    SessionEnded,
    SessionEvent,
    SessionFactory,
    SessionRefused,
    ToolCall,
    TranscriptDelta,
    Usage,
)

BYTES_PER_MS = BYTES_PER_S / 1000
SILENCE_MAX_S = 8.0  # longest silence streamed after a turn while waiting for the reply

_BUDGET_FIELDS = tuple(BudgetLimits.model_fields)


class GateRefused(Exception):
    """The gate refuses to start; no Boson session has been opened (AC-4, AC-46)."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class GateAborted(Exception):
    """The run cannot produce a record (server refused the session, or the stream broke)."""

    def __init__(self, error_text: str) -> None:
        super().__init__(error_text)
        self.error_text = error_text


def _budget_reasons(spec: AgentSpec) -> list[str]:
    reasons: list[str] = []
    budget = spec.budget
    for name in _BUDGET_FIELDS:
        if getattr(budget, name) <= 0:
            reasons.append(f"budget.{name}: must be greater than zero")
    count = len(spec.scenarios)
    if count > budget.max_scenarios:
        reasons.append(f"{count} scenarios exceed the limit of {budget.max_scenarios}")
    return reasons


def check_limits(spec: AgentSpec) -> None:
    reasons = _budget_reasons(spec)
    if reasons:
        raise GateRefused(reasons)


def preflight(raw: Mapping[str, Any]) -> AgentSpec:
    """Validate the raw spec and its budget before any session is opened."""
    result = validate_agent_spec(raw)
    if not isinstance(result, AgentSpec):
        reasons: list[str] = []
        for issue in result:
            if issue.field == "budget":  # whole block missing: name every limit (AC-4)
                reasons.extend(f"budget.{name}: missing" for name in _BUDGET_FIELDS)
            else:
                reasons.append(f"{issue.field}: {issue.message}")
        raise GateRefused(reasons)
    check_limits(result)
    return result


def expected_call_match(
    expected: ExpectedCall, calls: list[ToolCall]
) -> Literal["matched", "not matched"]:
    """AC-23: a call with this tool name whose arguments include every declared one.
    Recorded on the card only; it never changes the judge's label (AC-19)."""
    for call in calls:
        if call.name == expected.name and all(
            key in call.arguments and call.arguments[key] == value
            for key, value in expected.arguments.items()
        ):
            return "matched"
    return "not matched"


def select_mock(tool: ClientTool, arguments: dict[str, Any]) -> str:
    """First case whose `when` is a subset of the arguments, else the default output.
    Tool arguments only select among the spec's own mock outputs (AC-22)."""
    for case in tool.mock.by_argument:
        if all(key in arguments and arguments[key] == value for key, value in case.when.items()):
            return case.output
    return tool.mock.default_output


# --- run loop ------------------------------------------------------------------------------


class _Stop(Exception):
    """Internal: the run ends early with this cause (the record is still returned)."""

    def __init__(self, cause: Cause, detail: str | None = None) -> None:
        super().__init__(cause)
        self.cause = cause
        self.detail = detail


class _BudgetReached(_Stop):
    def __init__(self) -> None:
        super().__init__("budget reached")


@dataclass
class _Interrupt:
    pcm: bytes
    after_ms: int


@dataclass
class _Reply:
    ttfa_ms: float | None = None
    text: str = ""
    interrupt_last_chunk_t: float | None = None  # the interrupt turn was played during this reply
    bargein_ms: float | None = None


class _End:
    """Queue marker: the event stream ended."""


class _BudgetHit:
    """Queue marker: the audio budget was reached while the loop waited for an event."""


class _MeteredSession:
    """Counts input audio and raises once input + output reaches the per-run audio limit."""

    def __init__(self, session: RealtimeSession, limit_s: float, wake: asyncio.Queue[Any]) -> None:
        self._session = session
        self._limit_bytes = limit_s * BYTES_PER_S
        self._wake = wake
        self.input_bytes = 0
        self.output_bytes = 0
        self.first_send_t: float | None = None
        self._watching = False

    def watch_first_send(self) -> None:
        """Remember the send time of the next audio chunk (the barge-in mark, AC-28)."""
        self.first_send_t = None
        self._watching = True

    def over_budget(self) -> bool:
        return self.input_bytes + self.output_bytes >= self._limit_bytes

    async def open(self, spec: AgentSpec) -> None:
        await self._session.open(spec)

    async def send_audio(self, pcm: bytes) -> float:
        sent_at = await self._session.send_audio(pcm)
        self.input_bytes += len(pcm)
        if self._watching:
            self.first_send_t, self._watching = sent_at, False
        if self.over_budget():
            self._wake.put_nowait(_BudgetHit())  # wakes the loop if a silence task tripped it
            raise _BudgetReached
        return sent_at

    async def send_tool_output(self, call_id: str, output: str) -> None:
        await self._session.send_tool_output(call_id, output)

    def events(self) -> Any:
        return self._session.events()

    async def close(self) -> None:
        await self._session.close()


class _Run:
    def __init__(
        self,
        spec: AgentSpec,
        session: RealtimeSession,
        audio: TurnAudioSource,
        judge: JudgePort,
        sleep: Sleep,
    ) -> None:
        self.spec = spec
        self.audio = audio
        self.judge = judge
        self.sleep = sleep
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.session = _MeteredSession(session, spec.budget.max_audio_s_per_run, self.queue)
        self.client_tools = {t.name: t for t in spec.tools if isinstance(t, ClientTool)}
        self.scenarios: list[ScenarioRecord] = []
        self.turns: list[TurnRecord] = []
        self.usages: list[Usage | None] = []
        self.cause: Cause | None = None
        self.cause_detail: str | None = None
        self.carry: list[SessionEvent] = []  # events read early, replayed to the next reply
        self._pump_task: asyncio.Task[None] | None = None

    async def _pump(self) -> None:
        """Read the session's events into a queue so the loop never misses a close."""
        try:
            async for event in self.session.events():
                self.queue.put_nowait(event)
                if isinstance(event, SessionEnded):
                    return
        except Exception as exc:  # surfaced in the loop, not lost in the task
            self.queue.put_nowait(exc)
            return
        self.queue.put_nowait(_End())

    async def next_event(self) -> SessionEvent:
        if self.carry:
            return self.carry.pop(0)
        item = await self.queue.get()
        if isinstance(item, _BudgetHit):
            raise _BudgetReached
        if isinstance(item, _End):
            raise GateAborted("the session stream ended before the scenario finished")
        if isinstance(item, Exception):
            raise item
        if isinstance(item, SessionEnded):
            if item.cause == "closed":  # not one of the spec's incomplete causes
                raise GateAborted(item.error_text or "the session closed before the run ended")
            raise _Stop(item.cause, item.error_text)
        return item

    async def execute(self) -> None:
        self._pump_task = asyncio.create_task(self._pump())
        try:
            for scenario in self.spec.scenarios:
                await self._scenario(scenario)
        except _Stop as stop:
            self.cause, self.cause_detail = stop.cause, stop.detail

    async def shutdown(self) -> None:
        if self._pump_task is not None:
            self._pump_task.cancel()
            await asyncio.gather(self._pump_task, return_exceptions=True)
        await self.session.close()

    async def _audio(
        self, scenario: Scenario, index: int, cache: dict[int, tuple[bytes, str]]
    ) -> tuple[bytes, str]:
        if index not in cache:
            label = f"{scenario.id} turn {index + 1}"
            try:
                cache[index] = await self.audio.audio_for(
                    scenario.user_turns[index], scenario.user_voice, label=label
                )
            except AudioMissing as exc:
                detail = f"{exc.turn_label}: {exc.cause}" if exc.cause else exc.turn_label
                raise _Stop("audio missing", detail) from exc
        return cache[index]

    async def _scenario(self, scenario: Scenario) -> None:
        texts: list[str] = []
        calls: list[ToolCall] = []
        sources: set[str] = set()
        new_turns: list[TurnRecord] = []
        audio_cache: dict[int, tuple[bytes, str]] = {}
        played_at: float | None = None  # an interrupt turn already played over the last reply
        barge_in: tuple[float | None, Literal["measured", "not measured"] | None] = (None, None)
        turns = scenario.user_turns
        for index in range(len(turns)):
            pcm, source = await self._audio(scenario, index, audio_cache)
            sources.add(source)
            interrupt: _Interrupt | None = None
            if index + 1 < len(turns) and turns[index + 1].interrupt_after_assistant_ms is not None:
                next_pcm, _ = await self._audio(scenario, index + 1, audio_cache)
                interrupt = _Interrupt(next_pcm, turns[index + 1].interrupt_after_assistant_ms or 0)
            reply = await self._exchange(pcm, calls, interrupt=interrupt, played_at=played_at)
            texts.append(reply.text)
            new_turns.append(TurnRecord(scenario.id, index, "scripted", reply.ttfa_ms, *barge_in))
            played_at = reply.interrupt_last_chunk_t
            if interrupt is None:
                barge_in = (None, None)
            else:  # AC-28: the stop time belongs to the interrupting turn
                measured = reply.bargein_ms is not None
                barge_in = (reply.bargein_ms, "measured" if measured else "not measured")
        self.turns.extend(new_turns)
        request = JudgeRequest(
            rubric=scenario.rubric,
            user_turns=[t.text for t in turns],
            transcript="\n".join(texts),
            tool_calls=list(calls),
        )
        judgment = await judge_scenario(self.judge, request)  # exactly one call
        expected = scenario.expected_tool_call
        self.scenarios.append(
            ScenarioRecord(
                scenario_id=scenario.id,
                title=scenario.title,
                rubric=scenario.rubric,
                judgment=judgment,
                transcript=request.transcript,
                tool_calls=calls,
                expected_call_match=(
                    expected_call_match(expected, calls) if expected is not None else None
                ),
                audio_source="recorded" if "recorded" in sources else "synthesised",
            )
        )
        if judgment is None:
            raise _Stop("judge reply invalid", scenario.id)

    async def _exchange(
        self,
        pcm: bytes,
        calls: list[ToolCall],
        *,
        interrupt: "_Interrupt | None" = None,
        played_at: float | None = None,
    ) -> "_Reply":
        """Play one user turn (unless an earlier reply already played it as an interruption),
        stream silence until the reply starts, read the reply to its end."""
        if played_at is None:
            played_at = await play_turn(self.session, pcm, sleep=self.sleep)
        stop = asyncio.Event()
        silence = asyncio.create_task(
            stream_silence_until(self.session, stop, SILENCE_MAX_S, sleep=self.sleep)
        )
        try:
            reply = await self._read_reply(played_at, stop, calls, interrupt)
        finally:
            stop.set()
            await asyncio.gather(silence, return_exceptions=True)
        if self.session.over_budget():
            raise _BudgetReached
        return reply

    async def _read_reply(
        self,
        last_chunk_t: float,
        stop: asyncio.Event,
        calls: list[ToolCall],
        interrupt: "_Interrupt | None",
    ) -> "_Reply":
        reply = _Reply()
        parts: list[str] = []
        follow_up = False  # a client tool was answered, so another response is coming
        heard_ms: dict[str, float] = {}
        interrupted: str | None = None  # response id the interrupt turn was played over
        last_delta_t = 0.0
        play_task: asyncio.Task[float] | None = None
        try:
            while True:
                event = await self.next_event()
                rid = getattr(event, "response_id", None)
                if interrupted is not None and rid not in (None, interrupted):
                    self.carry.append(event)  # belongs to the reply to the interrupt turn
                    continue
                if isinstance(event, AudioDelta):
                    self.session.output_bytes += event.nbytes
                    if self.session.over_budget():
                        raise _BudgetReached
                    if reply.ttfa_ms is None:
                        reply.ttfa_ms = ttfa_ms(last_chunk_t, event.t)  # F17
                        stop.set()
                    heard_ms[event.response_id] = (
                        heard_ms.get(event.response_id, 0.0) + event.nbytes / BYTES_PER_MS
                    )
                    if (
                        interrupt is not None
                        and interrupted is None
                        and heard_ms[event.response_id] >= interrupt.after_ms
                    ):
                        interrupted = event.response_id  # AC-28: play over the running reply
                        self.session.watch_first_send()
                        play_task = asyncio.create_task(
                            play_turn(self.session, interrupt.pcm, sleep=self.sleep)
                        )
                    if interrupted == event.response_id:
                        last_delta_t = event.t
                elif isinstance(event, TranscriptDelta):
                    parts.append(event.text)
                elif isinstance(event, ToolCall):
                    calls.append(event)
                    tool = self.client_tools.get(event.name)
                    if event.executor == "client" and tool is not None:
                        await self.session.send_tool_output(
                            event.call_id, select_mock(tool, event.arguments)
                        )
                        follow_up = True
                elif isinstance(event, ResponseDone):
                    self.usages.append(event.usage)
                    if interrupted is not None and play_task is not None:
                        reply.interrupt_last_chunk_t = await play_task
                        mark = self.session.first_send_t
                        if mark is not None and last_delta_t > mark:
                            reply.bargein_ms = (last_delta_t - mark) * 1000.0
                        break
                    if not follow_up:
                        break
                    follow_up = False
                # SpeechStarted, SpeechStopped, OtherEvent: ignored (F5, AC-24)
        finally:
            if play_task is not None and not play_task.done():
                play_task.cancel()
                await asyncio.gather(play_task, return_exceptions=True)
        reply.text = "".join(parts)
        return reply

    def record(self, agent_id: str) -> GateRunRecord:
        ended_at = datetime.now(UTC)
        return GateRunRecord(
            agent_id=agent_id,
            run_id=f"{ended_at:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}",
            ended_at=ended_at,
            scenarios=self.scenarios,
            turns=self.turns,
            usages=self.usages,
            input_audio_s=self.session.input_bytes / BYTES_PER_S,
            output_audio_s=self.session.output_bytes / BYTES_PER_S,
            cause=self.cause,
            cause_detail=self.cause_detail,
        )


async def run_gate(
    spec: AgentSpec,
    *,
    sessions: SessionFactory,
    audio: TurnAudioSource,
    judge: JudgePort,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
) -> GateRunRecord:
    """One session per run. A cut-short run returns a record with `cause` set; a refused
    session raises `GateAborted` and yields no record (AC-20).

    `clock` is accepted for the plan's signature; every timestamp the loop needs (send times,
    event times) comes from the session, so it is not read here.
    """
    check_limits(spec)
    session = sessions()
    try:
        await session.open(spec)
    except SessionRefused as exc:
        await session.close()
        raise GateAborted(exc.error_text) from exc
    run = _Run(spec, session, audio, judge, sleep)
    try:
        await run.execute()
    finally:
        await run.shutdown()
    return run.record(spec.id)
