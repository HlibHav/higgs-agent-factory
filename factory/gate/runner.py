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
from dataclasses import dataclass, field
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
from factory.gate.judge import judge_scenario_agreed
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
FOLLOW_UP_WINDOW_S = 10.0  # longest wait for the reply that follows a tool output
QUIET_WINDOW_S: float = (
    2.0  # AC-57: a turn ends this long after the last response; read at call time
)

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
    response_ids: list[str] = field(default_factory=list)  # in start order
    interrupt_last_chunk_t: float | None = None  # the interrupt turn was played during this reply
    bargein_ms: float | None = None


class _End:
    """Queue marker: the event stream ended."""


class _BudgetHit:
    """Queue marker: the audio budget was reached while the loop waited for an event."""


class _Meter:
    """Run-wide audio count: input and output bytes of every scenario session (AC-56)."""

    def __init__(self, limit_s: float) -> None:
        self._limit_bytes = limit_s * BYTES_PER_S
        self.input_bytes = 0
        self.output_bytes = 0

    def over_budget(self) -> bool:
        return self.input_bytes + self.output_bytes >= self._limit_bytes


class _MeteredSession:
    """Counts input audio into the shared meter and raises once the per-run limit is hit."""

    def __init__(self, session: RealtimeSession, meter: _Meter, wake: asyncio.Queue[Any]) -> None:
        self._session = session
        self._meter = meter
        self._wake = wake
        self.first_send_t: float | None = None
        self._watching = False

    def watch_first_send(self) -> None:
        """Remember the send time of the next audio chunk (the barge-in mark, AC-28)."""
        self.first_send_t = None
        self._watching = True

    def over_budget(self) -> bool:
        return self._meter.over_budget()

    def add_output(self, nbytes: int) -> None:
        self._meter.output_bytes += nbytes

    async def open(self, spec: AgentSpec) -> None:
        await self._session.open(spec)

    async def send_audio(self, pcm: bytes) -> float:
        sent_at = await self._session.send_audio(pcm)
        self._meter.input_bytes += len(pcm)
        if self._watching:
            self.first_send_t, self._watching = sent_at, False
        if self._meter.over_budget():
            self._wake.put_nowait(_BudgetHit())  # wakes the loop if a silence task tripped it
            raise _BudgetReached
        return sent_at

    async def send_tool_output(self, call_id: str, output: str) -> None:
        await self._session.send_tool_output(call_id, output)

    def events(self) -> Any:
        return self._session.events()

    async def close(self) -> None:
        await self._session.close()


class _ScenarioSession:
    """What lives for one scenario (AC-55): its session, event queue, carry and pump."""

    def __init__(self, factory: SessionFactory, meter: _Meter) -> None:
        self._factory = factory
        self._meter = meter
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.carry: list[SessionEvent] = []  # events read early, replayed to the next reply
        self.session: _MeteredSession | None = None
        self._raw: RealtimeSession | None = None
        self._pump_task: asyncio.Task[None] | None = None

    async def open(self, spec: AgentSpec) -> _MeteredSession:
        raw = self._factory()
        self._raw = raw
        try:
            await raw.open(spec)
        except SessionRefused as exc:
            await raw.close()
            raise GateAborted(exc.error_text) from exc
        self.session = _MeteredSession(raw, self._meter, self.queue)
        self._pump_task = asyncio.create_task(self._pump())
        return self.session

    async def _pump(self) -> None:
        """Read the session's events into a queue so the loop never misses a close."""
        assert self.session is not None
        try:
            async for event in self.session.events():
                self.queue.put_nowait(event)
                if isinstance(event, SessionEnded):
                    return
        except Exception as exc:  # surfaced in the loop, not lost in the task
            self.queue.put_nowait(exc)
            return
        self.queue.put_nowait(_End())

    async def next_event(
        self, timeout: float | None = None, *, in_window: bool = False
    ) -> SessionEvent | None:
        """The next event; None when `timeout` seconds pass first. Carry is drained first.
        Inside the quiet window a finished stream also ends the wait (nothing more can come);
        the end marker stays queued so the next read still aborts."""
        if self.carry:
            return self.carry.pop(0)
        try:
            item = await asyncio.wait_for(self.queue.get(), timeout)
        except TimeoutError:
            return None
        if isinstance(item, _BudgetHit):
            raise _BudgetReached
        if isinstance(item, _End):
            if in_window:
                self.queue.put_nowait(item)
                return None
            raise GateAborted("the session stream ended before the scenario finished")
        if isinstance(item, Exception):
            raise item
        if isinstance(item, SessionEnded):
            if item.cause == "closed":  # not one of the spec's incomplete causes
                raise GateAborted(item.error_text or "the session closed before the run ended")
            raise _Stop(item.cause, item.error_text)
        return item

    async def shutdown(self) -> None:
        if self._pump_task is not None:
            self._pump_task.cancel()
            await asyncio.gather(self._pump_task, return_exceptions=True)
        if self._raw is not None:
            await self._raw.close()


class _Run:
    def __init__(
        self,
        spec: AgentSpec,
        sessions: SessionFactory,
        audio: TurnAudioSource,
        judge: JudgePort,
        sleep: Sleep,
        caller_voice: str | None = None,
    ) -> None:
        self.caller_voice = caller_voice  # AC-80: overrides every scenario's user_voice
        self.spec = spec
        self.sessions = sessions
        self.audio = audio
        self.judge = judge
        self.sleep = sleep
        self.meter = _Meter(spec.budget.max_audio_s_per_run)
        self.client_tools = {t.name: t for t in spec.tools if isinstance(t, ClientTool)}
        self.scenarios: list[ScenarioRecord] = []
        self.turns: list[TurnRecord] = []
        self.usages: list[Usage | None] = []
        self.cause: Cause | None = None
        self.cause_detail: str | None = None
        self._current: _ScenarioSession | None = None

    @property
    def scenario_session(self) -> _ScenarioSession:
        assert self._current is not None
        return self._current

    @property
    def session(self) -> _MeteredSession:
        assert self._current is not None and self._current.session is not None
        return self._current.session

    async def next_event(
        self, timeout: float | None = None, *, in_window: bool = False
    ) -> SessionEvent | None:
        return await self.scenario_session.next_event(timeout, in_window=in_window)

    async def execute(self) -> None:
        try:
            for scenario in self.spec.scenarios:
                await self._scenario(scenario)
        except _Stop as stop:
            self.cause, self.cause_detail = stop.cause, stop.detail

    async def _audio(
        self, scenario: Scenario, index: int, cache: dict[int, tuple[bytes, str]]
    ) -> tuple[bytes, str]:
        if index not in cache:
            label = f"{scenario.id} turn {index + 1}"
            try:
                cache[index] = await self.audio.audio_for(
                    scenario.user_turns[index],
                    self.caller_voice or scenario.user_voice,
                    label=label,
                )
            except AudioMissing as exc:
                detail = f"{exc.turn_label}: {exc.cause}" if exc.cause else exc.turn_label
                raise _Stop("audio missing", detail) from exc
        return cache[index]

    async def _scenario(self, scenario: Scenario) -> None:
        current = _ScenarioSession(self.sessions, self.meter)
        self._current = current
        try:
            await current.open(self.spec)
            await self._scenario_turns(scenario)
        finally:
            await current.shutdown()  # a late response dies with its session

    async def _scenario_turns(self, scenario: Scenario) -> None:
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
            new_turns.append(
                TurnRecord(
                    scenario.id,
                    index,
                    "scripted",
                    reply.ttfa_ms,
                    *barge_in,
                    responses=len(reply.response_ids),
                )
            )
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
        k = max(1, self.spec.budget.max_judge_calls_per_scenario)  # AC-75, within budget
        outcome = await judge_scenario_agreed(self.judge, request, k)
        judgment = outcome.judgment
        skill = self.spec.skill_of(scenario.id)
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
                judge_raw_reply=outcome.raw_reply if judgment is None else None,
                judge_raw_truncated=outcome.raw_truncated if judgment is None else False,
                transcript_chars=len(request.transcript) if judgment is None else None,
                skill_id=skill.id if skill else "main",
                skill_name=skill.name if skill else "Main",
                judge_labels=outcome.labels,
                judge_agreed=outcome.agreed,
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
        texts: dict[str, list[str]] = {}
        follow_up = False  # a client tool was answered, so another response is coming
        heard_ms: dict[str, float] = {}
        interrupted: str | None = None  # response id the interrupt turn was played over
        last_delta_t = 0.0
        play_task: asyncio.Task[float] | None = None
        window_end: float | None = None  # AC-57: the quiet window runs until this loop time
        window_stop = asyncio.Event()
        window_task: asyncio.Task[None] | None = None
        loop = asyncio.get_running_loop()

        async def close_window() -> None:
            nonlocal window_end, window_task
            window_end = None
            window_stop.set()
            if window_task is not None:
                await asyncio.gather(window_task, return_exceptions=True)
                window_task = None

        try:
            while True:
                timeout = None if window_end is None else max(0.0, window_end - loop.time())
                event = await self.next_event(timeout, in_window=window_end is not None)
                if event is None:
                    break  # the quiet window elapsed: the turn is over
                rid = getattr(event, "response_id", None)
                if interrupted is not None and rid not in (None, interrupted):
                    self.scenario_session.carry.append(event)  # reply to the interrupt turn
                    continue
                if rid is not None and rid not in texts:  # F17: a new response starts here
                    texts[rid] = []
                    reply.response_ids.append(rid)
                    if window_end is not None:
                        await close_window()
                if isinstance(event, AudioDelta):
                    self.session.add_output(event.nbytes)
                    if self.session.over_budget():
                        raise _BudgetReached
                    if reply.ttfa_ms is None and event.response_id == reply.response_ids[0]:
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
                    texts[event.response_id].append(event.text)  # F18
                elif isinstance(event, ToolCall):
                    calls.append(event)
                    tool = self.client_tools.get(event.name)
                    if event.executor == "client" and tool is not None:
                        await self.session.send_tool_output(
                            event.call_id, select_mock(tool, event.arguments)
                        )
                        follow_up = True
                        if window_end is not None:
                            await close_window()  # the follow-up is awaited without a timeout
                elif isinstance(event, ResponseDone):
                    self.usages.append(event.usage)
                    if interrupted is not None and play_task is not None:
                        reply.interrupt_last_chunk_t = await play_task
                        mark = self.session.first_send_t
                        # AC-29: only a cancelled response counts as stopped by the interruption
                        if event.status == "cancelled" and mark is not None and last_delta_t > mark:
                            reply.bargein_ms = (last_delta_t - mark) * 1000.0
                        break
                    if not follow_up:
                        stop.set()  # no more waiting-for-reply silence
                        await close_window()
                        window_stop.clear()
                        window_end = loop.time() + QUIET_WINDOW_S
                        window_task = asyncio.create_task(
                            stream_silence_until(
                                self.session, window_stop, QUIET_WINDOW_S, sleep=self.sleep
                            )
                        )
                    else:
                        # A tool call answered: wait for the follow-up response, but never
                        # forever. The window closes as soon as the follow-up starts.
                        follow_up = False
                        await close_window()
                        window_stop.clear()
                        window_end = loop.time() + FOLLOW_UP_WINDOW_S
                        window_task = asyncio.create_task(
                            stream_silence_until(
                                self.session, window_stop, FOLLOW_UP_WINDOW_S, sleep=self.sleep
                            )
                        )
                # ResponseCreated, SpeechStarted, SpeechStopped, OtherEvent: no action (F5, AC-24)
        finally:
            window_stop.set()
            if window_task is not None:
                await asyncio.gather(window_task, return_exceptions=True)
            if play_task is not None and not play_task.done():
                play_task.cancel()
                await asyncio.gather(play_task, return_exceptions=True)
        reply.text = " ".join(t for t in ("".join(texts[r]) for r in reply.response_ids) if t)
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
            input_audio_s=self.meter.input_bytes / BYTES_PER_S,
            output_audio_s=self.meter.output_bytes / BYTES_PER_S,
            cause=self.cause,
            cause_detail=self.cause_detail,
            agent_version=self.spec.version,
            agent_spec=self.spec.model_dump(mode="json"),
        )


async def run_gate(
    spec: AgentSpec,
    *,
    sessions: SessionFactory,
    audio: TurnAudioSource,
    judge: JudgePort,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
    caller_voice: str | None = None,
) -> GateRunRecord:
    """One session per scenario (AC-55), one audio meter for the run (AC-56). A cut-short run
    returns a record with `cause` set; a refused session raises `GateAborted` and yields no
    record (AC-20).

    `clock` is accepted for the plan's signature; every timestamp the loop needs (send times,
    event times) comes from the session, so it is not read here.
    """
    check_limits(spec)
    run = _Run(spec, sessions, audio, judge, sleep, caller_voice)
    await run.execute()
    return run.record(spec.id)
