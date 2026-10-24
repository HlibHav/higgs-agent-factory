"""Gate runner: preflight (step 12) and the run loop (steps 16, 17b, 17c)."""

import asyncio
import json
import time
import wave
from pathlib import Path
from typing import Any

import pytest

from factory.agent_spec.models import AgentSpec, ArgCase, ClientTool, ExpectedCall, MockBehaviour
from factory.gate import runner
from factory.gate.card_builder import build_card
from factory.gate.records import GateRunRecord
from factory.gate.render import render_card_text
from factory.gate.runner import (
    GateAborted,
    GateRefused,
    expected_call_match,
    preflight,
    run_gate,
    select_mock,
)
from factory.gate.tts_cache import TurnAudioSource
from factory.ports import (
    AudioDelta,
    OtherEvent,
    ResponseCreated,
    ResponseDone,
    SessionEnded,
    ToolCall,
    TranscriptDelta,
    Usage,
)
from tests.doubles import Delay, FakeJudge, FakeSessionFactory, FakeTts, Refuse, make_spec

GOOD = json.dumps({"label": "PASS", "rationale": "ok", "evidence": "Hello"})
BAD = json.dumps({"label": "MAYBE"})
BYTES_PER_S = 48_000


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)  # yield like a real sleep, so the silence task shares the loop


@pytest.fixture(autouse=True)
def _short_quiet_window(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("real_window") is None:
        monkeypatch.setattr(runner, "QUIET_WINDOW_S", 0.05)


def test_ac4_missing_budget_refused_no_session(session_factory: FakeSessionFactory) -> None:
    raw = make_spec()
    del raw["budget"]
    with pytest.raises(GateRefused) as info:
        preflight(raw)
    text = " ".join(info.value.reasons)
    for name in (
        "budget.max_scenarios",
        "budget.max_audio_s_per_run",
        "budget.max_judge_calls_per_scenario",
        "budget.max_live_session_s",
    ):
        assert name in text
    assert session_factory.calls == 0


def test_ac4_one_missing_budget_field_is_named() -> None:
    raw = make_spec()
    del raw["budget"]["max_audio_s_per_run"]
    with pytest.raises(GateRefused) as info:
        preflight(raw)
    assert any("budget.max_audio_s_per_run" in r for r in info.value.reasons)
    assert not any("budget.max_scenarios" in r for r in info.value.reasons)


def test_ac46_too_many_scenarios(session_factory: FakeSessionFactory) -> None:
    raw = make_spec()
    scenario = raw["scenarios"][0]
    raw["scenarios"] = [{**scenario, "id": f"s{i}"} for i in range(7)]
    with pytest.raises(GateRefused) as info:
        preflight(raw)
    assert "7 scenarios exceed the limit of 6" in str(info.value)
    assert session_factory.calls == 0


def test_non_positive_judge_budget_refused() -> None:
    raw = make_spec()
    raw["budget"]["max_judge_calls_per_scenario"] = 0
    with pytest.raises(GateRefused) as info:
        preflight(raw)
    assert any("budget.max_judge_calls_per_scenario" in r for r in info.value.reasons)


def test_valid_spec_passes_preflight() -> None:
    spec = preflight(make_spec())
    assert spec.id == "agent-1"


# --- run loop (step 16) --------------------------------------------------------------------

LOOKUP_TOOL = {
    "kind": "client",
    "name": "lookup",
    "description": "Look an order up",
    "parameters": {"type": "object"},
    "mock": {
        "default_output": '{"status": "unknown"}',
        "by_argument": [{"when": {"order": "A1"}, "output": '{"status": "packed"}'}],
    },
}


def reply(
    rid: str = "r1",
    *,
    text: str = "Hello, welcome.",
    nbytes: int = 4800,
    t: float = 1000.4,
    usage: Usage | None = None,
) -> list:
    return [
        AudioDelta(rid, nbytes, t),
        TranscriptDelta(rid, text, t),
        ResponseDone(rid, "completed", usage, t + 0.1),
    ]


def two_scenarios() -> dict[str, Any]:
    raw = make_spec()
    second = {**raw["scenarios"][0], "id": "s2", "title": "Second"}
    raw["scenarios"] = [raw["scenarios"][0], second]
    return raw


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        raw: dict[str, Any],
        script: list,
        judge_replies: list[str],
        tts: FakeTts | None = None,
        *,
        scripts: list[list] | None = None,
        restamp: bool = False,
        real_time: bool = False,
    ) -> None:
        self.clock = FakeClock()
        self.now = time.monotonic if real_time else self.clock
        self.sleep = asyncio.sleep if real_time else self.clock.sleep
        self.spec: AgentSpec = preflight(raw)
        self.factory = FakeSessionFactory(script, clock=self.now, scripts=scripts, restamp=restamp)
        self.tts = tts or FakeTts()
        self.judge = FakeJudge(judge_replies)
        self.audio = TurnAudioSource(self.tts, tmp_path / "cache", tmp_path / "rec")

    def run(self) -> GateRunRecord:
        return asyncio.run(
            run_gate(
                self.spec,
                sessions=self.factory,
                audio=self.audio,
                judge=self.judge,
                sleep=self.sleep,
            )
        )


def test_happy_path_records_scenario_ttfa_usage_and_audio(tmp_path: Path) -> None:
    usage = Usage(10, 2, 5)
    h = Harness(tmp_path, make_spec(), reply(usage=usage), [GOOD])
    record = h.run()
    assert record.cause is None and record.agent_id == "agent-1"
    (scenario,) = record.scenarios
    assert scenario.judgment is not None and scenario.judgment.label == "PASS"
    assert scenario.transcript == "Hello, welcome."
    assert scenario.audio_source == "synthesised"
    (turn,) = record.turns
    assert (turn.scenario_id, turn.turn_index, turn.kind) == ("s1", 0, "scripted")
    assert turn.ttfa_ms is not None and abs(turn.ttfa_ms - 400.0) <= 50.0  # AC-25 in the loop
    assert record.usages == [usage]
    assert record.input_audio_s >= 4800 / BYTES_PER_S  # the turn plus whatever silence ran
    assert record.output_audio_s == pytest.approx(4800 / BYTES_PER_S)
    assert h.factory.calls == len(h.spec.scenarios) and h.factory.sessions[0].closed  # AC-55
    assert len(h.judge.requests) == 1
    assert h.judge.requests[0].user_turns == ["Hello there."]


def test_one_judge_call_per_scenario_budget(tmp_path: Path) -> None:
    raw = two_scenarios()
    h = Harness(tmp_path, raw, reply("r1") + reply("r2"), [GOOD, GOOD])
    record = h.run()
    assert len(record.scenarios) == 2
    assert len(h.judge.requests) == 2 * raw["budget"]["max_judge_calls_per_scenario"]


def test_run_gate_rechecks_limits_before_opening_a_session(tmp_path: Path) -> None:
    raw = two_scenarios()
    h = Harness(tmp_path, raw, [], [])
    over = h.spec.with_scenarios(h.spec.scenarios * 4)
    with pytest.raises(GateRefused):
        asyncio.run(run_gate(over, sessions=h.factory, audio=h.audio, judge=h.judge))
    assert h.factory.calls == 0


def test_ac10_no_audio_incomplete_names_turn(tmp_path: Path) -> None:
    h = Harness(tmp_path, make_spec(), reply(), [GOOD], tts=FakeTts(fail_texts={"Hello there."}))
    record = h.run()
    assert record.cause == "audio missing"
    assert record.cause_detail == "s1 turn 1: fake TTS failure for 'Hello there.'"
    assert record.scenarios == [] and h.judge.requests == []
    assert h.factory.sessions[0].sends == []


def test_ac9_recorded_fallback_continues_run_and_marks_scenario(tmp_path: Path) -> None:
    (tmp_path / "rec").mkdir()
    with wave.open(str(tmp_path / "rec" / "hello.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x03\x00" * 2400)
    raw = make_spec()
    raw["scenarios"][0]["user_turns"] = [{"text": "Hello there.", "recording": "hello.wav"}]
    h = Harness(tmp_path, raw, reply(), [GOOD], tts=FakeTts(fail_texts={"Hello there."}))
    record = h.run()
    assert record.cause is None
    assert record.scenarios[0].audio_source == "recorded"


@pytest.mark.parametrize(
    ("cause", "code", "text"),
    [
        ("quota refused", 4429, "insufficient_quota"),  # F13, AC-14
        ("idle timeout", 1000, "session.idle_timeout"),  # F8, AC-15
        ("concurrency limit", 1013, None),  # F21, AC-16
    ],
)
def test_session_end_causes_are_incomplete(
    tmp_path: Path, cause: str, code: int, text: str | None
) -> None:
    ended = SessionEnded(cause, code, text, 1000.2)  # type: ignore[arg-type]
    h = Harness(tmp_path, make_spec(), [ended], [GOOD])
    record = h.run()
    assert record.cause == cause
    assert record.cause_detail == text
    assert record.scenarios == [] and h.judge.requests == []
    assert h.factory.calls == 1  # no reconnect


def test_ac14_quota_refused_incomplete(tmp_path: Path) -> None:
    ended = SessionEnded("quota refused", 4429, "insufficient_quota", 1000.2)
    h = Harness(tmp_path, two_scenarios(), [], [GOOD], scripts=[reply("r1"), [ended]])
    record = h.run()
    assert record.cause == "quota refused"
    assert len(record.scenarios) == 1  # the first scenario finished and was judged


def test_ac15_idle_timeout_incomplete(tmp_path: Path) -> None:
    ended = SessionEnded("idle timeout", 1000, None, 1000.2)
    assert Harness(tmp_path, make_spec(), [ended], [GOOD]).run().cause == "idle timeout"


def test_ac16_concurrency_limit_incomplete(tmp_path: Path) -> None:
    ended = SessionEnded("concurrency limit", 1013, None, 1000.2)
    assert Harness(tmp_path, make_spec(), [ended], [GOOD]).run().cause == "concurrency limit"


def test_stream_ending_without_session_ended_aborts(tmp_path: Path) -> None:
    h = Harness(tmp_path, make_spec(), [], [GOOD])
    with pytest.raises(GateAborted):
        h.run()
    assert h.factory.sessions[0].closed


def test_ac17_audio_budget_reached(tmp_path: Path) -> None:
    raw = make_spec()
    raw["budget"]["max_audio_s_per_run"] = 0.05  # below one 100 ms turn
    h = Harness(tmp_path, raw, reply(), [GOOD])
    record = h.run()
    assert record.cause == "budget reached"
    assert record.scenarios == [] and h.judge.requests == []


def test_ac17_output_audio_counts_toward_the_budget(tmp_path: Path) -> None:
    raw = make_spec()
    raw["budget"]["max_audio_s_per_run"] = 0.25
    h = Harness(tmp_path, raw, reply(nbytes=9600), [GOOD])  # 0.1 s in + 0.2 s out
    record = h.run()
    assert record.cause == "budget reached"
    assert record.output_audio_s == pytest.approx(0.2)


def test_ac20_refused_voice_no_scenario_not_released(tmp_path: Path) -> None:
    h = Harness(tmp_path, make_spec(), [Refuse("voice 'zzz' is not available")], [GOOD])
    with pytest.raises(GateAborted) as info:
        h.run()
    assert info.value.error_text == "voice 'zzz' is not available"
    assert h.factory.sessions[0].sends == [] and h.tts.requests == []
    assert h.judge.requests == []


def test_ac22_client_tool_gets_mock(tmp_path: Path) -> None:
    raw = make_spec(tools=[LOOKUP_TOOL])
    call = ToolCall("c1", "lookup", {"order": "A1"}, "client", 1000.3)
    script = [call, ResponseDone("r0", "completed", None, 1000.35), *reply("r1")]
    h = Harness(tmp_path, raw, script, [GOOD])
    record = h.run()
    sends = h.factory.sessions[0].sends
    outputs = [s for s in sends if s.kind == "tool_output"]
    assert [(o.call_id, o.output) for o in outputs] == [("c1", '{"status": "packed"}')]
    assert record.scenarios[0].tool_calls == [call]
    assert record.cause is None
    assert len(record.usages) == 2  # both responses counted
    assert len(record.turns) == 1  # the follow-up response is the same user turn


def test_server_tool_call_is_observed_but_gets_no_output(tmp_path: Path) -> None:
    call = ToolCall("w1", "web_search", {"q": "x"}, "server", 1000.3)  # F10
    h = Harness(tmp_path, make_spec(), [call, *reply()], [GOOD])
    record = h.run()
    assert [s for s in h.factory.sessions[0].sends if s.kind == "tool_output"] == []
    assert record.scenarios[0].tool_calls == [call]


def test_ac24_unknown_event_ignored(tmp_path: Path) -> None:
    script = [OtherEvent("rate_limits.updated", 1000.1), *reply()]  # F5
    record = Harness(tmp_path, make_spec(), script, [GOOD]).run()
    assert record.cause is None and len(record.scenarios) == 1


def test_invalid_judgment_is_incomplete_and_stops_the_run(tmp_path: Path) -> None:
    h = Harness(tmp_path, two_scenarios(), reply("r1") + reply("r2"), [BAD, GOOD])
    record = h.run()
    assert record.cause == "judge reply invalid"
    assert record.cause_detail == "s1"
    assert len(h.judge.requests) == 1  # no retry, no second scenario
    assert record.scenarios[0].judgment is None


def test_ac62_invalid_reply_and_transcript_length_in_record(tmp_path: Path) -> None:
    h = Harness(tmp_path, make_spec(), reply("r1", text="a" * 412), [BAD])
    record = h.run()
    assert record.cause == "judge reply invalid"
    sc = record.scenarios[0]
    assert sc.judge_raw_reply == '{"label": "MAYBE"}'
    assert sc.judge_raw_truncated is False
    assert sc.transcript_chars == 412


def test_select_mock_first_matching_case_else_default() -> None:
    tool = ClientTool(
        name="t",
        description="d",
        parameters={},
        mock=MockBehaviour(
            default_output="default",
            by_argument=[
                ArgCase(when={"a": 1}, output="one"),
                ArgCase(when={"a": 1, "b": 2}, output="never reached"),
                ArgCase(when={"b": 2}, output="two"),
            ],
        ),
    )
    assert select_mock(tool, {"a": 1, "b": 2}) == "one"
    assert select_mock(tool, {"b": 2}) == "two"
    assert select_mock(tool, {"a": 9}) == "default"
    assert select_mock(tool, {}) == "default"


# --- expected tool call (step 17b) ----------------------------------------------------------


def test_ac23_expected_call_matched_and_not() -> None:
    call = ToolCall("c1", "lookup", {"order": "A1", "extra": 1}, "client", 1.0)
    assert (
        expected_call_match(ExpectedCall(name="lookup", arguments={"order": "A1"}), [call])
        == "matched"
    )
    assert expected_call_match(ExpectedCall(name="lookup"), [call]) == "matched"
    assert (
        expected_call_match(ExpectedCall(name="lookup", arguments={"order": "B2"}), [call])
        == "not matched"
    )
    assert expected_call_match(ExpectedCall(name="other"), [call]) == "not matched"
    assert expected_call_match(ExpectedCall(name="lookup"), []) == "not matched"


def _expected_spec(arguments: dict[str, Any]) -> dict[str, Any]:
    raw = make_spec(tools=[LOOKUP_TOOL])
    raw["scenarios"][0]["expected_tool_call"] = {"name": "lookup", "arguments": arguments}
    return raw


def test_ac23_record_carries_match_and_never_changes_the_label(tmp_path: Path) -> None:
    call = ToolCall("c1", "lookup", {"order": "A1"}, "client", 1000.3)
    done = ResponseDone("r0", "completed", None, 1000.35)
    matched = Harness(
        tmp_path, _expected_spec({"order": "A1"}), [call, done, *reply()], [GOOD]
    ).run()
    assert matched.scenarios[0].expected_call_match == "matched"
    missed = Harness(tmp_path, _expected_spec({"order": "A1"}), reply(), [GOOD]).run()
    assert missed.scenarios[0].expected_call_match == "not matched"
    assert missed.scenarios[0].judgment is not None
    assert missed.scenarios[0].judgment.label == "PASS"  # AC-19: the judge's label stands
    plain = Harness(tmp_path, make_spec(), reply(), [GOOD]).run()
    assert plain.scenarios[0].expected_call_match is None


# --- one session per scenario (16d, AC-55, AC-56) -------------------------------------------


class LetterTts(FakeTts):
    """PCM derived from the text: the first letter's code, `seconds` long."""

    def __init__(self, seconds: float = 0.1) -> None:
        super().__init__()
        self.seconds = seconds

    async def synthesise(self, text: str, voice: str) -> bytes:
        self.requests.append((text, voice))
        return bytes([ord(text[0]), 0]) * int(24000 * self.seconds)


def _three_scenarios(texts: list[str]) -> dict[str, Any]:
    raw = make_spec()
    base = raw["scenarios"][0]
    raw["scenarios"] = [
        {**base, "id": f"s{i + 1}", "user_turns": [{"text": text}]} for i, text in enumerate(texts)
    ]
    return raw


def test_ac55_one_session_per_scenario(tmp_path: Path) -> None:
    texts = ["Alpha one.", "Bravo two.", "Charlie three."]
    scripts = [reply(f"r{i}", text=f"reply-{i}") for i in (1, 2, 3)]
    h = Harness(tmp_path, _three_scenarios(texts), [], [GOOD] * 3, tts=LetterTts(), scripts=scripts)
    record = h.run()
    assert record.cause is None and len(record.scenarios) == 3
    assert h.factory.calls == 3
    assert all(session.closed for session in h.factory.sessions)
    for session, text in zip(h.factory.sessions, texts, strict=True):
        speech = {s.pcm for s in session.sends if s.pcm and any(s.pcm)}
        assert speech == {bytes([ord(text[0]), 0]) * 2400}  # only its own scenario's speech
    assert [r.transcript for r in h.judge.requests] == ["reply-1", "reply-2", "reply-3"]


def test_ac56_budget_sums_across_sessions(tmp_path: Path) -> None:
    raw = _three_scenarios(["Alpha one.", "Bravo two.", "Charlie three."])
    raw["budget"]["max_audio_s_per_run"] = 10.0
    scripts = [reply(f"r{i}") for i in (1, 2, 3)]
    h = Harness(tmp_path, raw, [], [GOOD] * 3, tts=LetterTts(4.0), scripts=scripts)
    record = h.run()
    assert record.cause == "budget reached"
    assert len(record.scenarios) == 2
    assert h.factory.calls == 3  # the stop happened inside the third
    assert record.input_audio_s + record.output_audio_s >= 10.0 - 0.01


# --- quiet window (16e, AC-57, AC-58, AC-60) ------------------------------------------------


def _created(rid: str) -> ResponseCreated:
    return ResponseCreated(rid, 0.0)


def _response(rid: str, text: str = "") -> list:
    items: list = [_created(rid), AudioDelta(rid, 4800, 0.0)]
    if text:
        items.append(TranscriptDelta(rid, text, 0.0))
    return [*items, ResponseDone(rid, "completed", None, 0.0)]


@pytest.mark.real_window
def test_quiet_window_default_is_two_seconds() -> None:
    assert runner.QUIET_WINDOW_S == 2.0


@pytest.mark.real_window
def test_ac57_turn_ends_two_seconds_after_last_response(tmp_path: Path) -> None:
    raw = make_spec()
    raw["scenarios"][0]["user_turns"] = [{"text": "Alpha one."}, {"text": "Bravo two."}]
    script = [*_response("A"), Delay(1.2), *_response("B"), Delay(3.0), *_response("C")]
    h = Harness(tmp_path, raw, script, [GOOD], tts=LetterTts(), restamp=True, real_time=True)
    record = h.run()
    assert record.cause is None
    sends = h.factory.sessions[0].sends
    first = next(s for s in sends if s.pcm and s.pcm[0] == ord("A"))
    second = next(s for s in sends if s.pcm and s.pcm[0] == ord("B"))
    b_done = first.t + 1.2  # the stream starts with the first send, give or take a few ms
    assert second.t >= b_done + 2.0 - 0.1
    assert second.t - first.t > 2.0 + 0.5  # not within 2 s of A's done


@pytest.mark.real_window
def test_ac58_split_reply_joined_for_its_own_scenario_only(tmp_path: Path) -> None:
    raw = _three_scenarios(["Alpha one.", "Bravo two."])
    st5 = [
        *_response("A", "No problem."),
        Delay(1.0),
        *_response("B", "Acknowledge their feeling first, then say what you will fix."),
    ]
    st6 = _response("C", "Sure, here is the answer.")
    h = Harness(
        tmp_path,
        raw,
        [],
        [GOOD] * 2,
        tts=LetterTts(),
        scripts=[st5, st6],
        restamp=True,
        real_time=True,
    )
    record = h.run()
    assert record.cause is None
    first, second = (r.transcript for r in h.judge.requests)
    assert first == ("No problem. Acknowledge their feeling first, then say what you will fix.")
    assert "No problem." not in second and "Acknowledge" not in second
    assert second == "Sure, here is the answer."


@pytest.mark.real_window
def test_ac60_window_silence_counts_toward_budget(tmp_path: Path) -> None:
    h = Harness(
        tmp_path,
        make_spec(),
        [*_response("A", "Hi."), Delay(3.0)],
        [GOOD],
        tts=LetterTts(1.0),
        restamp=True,
        real_time=True,
    )
    record = h.run()
    assert record.cause is None
    assert record.input_audio_s >= 1.0 + 2.0 - 0.15


@pytest.mark.real_window
def test_ac59_ttfa_on_first_response_only(tmp_path: Path) -> None:
    script = [
        Delay(0.4),
        _created("A"),
        AudioDelta("A", 4800, 0.0),
        ResponseDone("A", "completed", None, 0.0),
        Delay(1.2),
        _created("B"),
        AudioDelta("B", 4800, 0.0),
        ResponseDone("B", "completed", None, 0.0),
        Delay(3.0),
    ]
    h = Harness(tmp_path, make_spec(), script, [GOOD], restamp=True, real_time=True)
    record = h.run()
    (turn,) = record.turns
    assert turn.ttfa_ms is not None and abs(turn.ttfa_ms - 400.0) <= 50.0


@pytest.mark.real_window
def test_ac61_responses_per_turn_recorded_and_shown(tmp_path: Path) -> None:
    raw = make_spec()
    raw["scenarios"][0]["user_turns"] = [{"text": "Alpha one."}, {"text": "Bravo two."}]
    script = [
        *_response("A", "One."),
        Delay(0.5),
        *_response("B", "Two."),
        Delay(2.6),  # past the window of turn 1
        *_response("C", "Three."),
        Delay(3.0),
    ]
    h = Harness(tmp_path, raw, script, [GOOD], tts=LetterTts(), restamp=True, real_time=True)
    record = h.run()
    assert [t.responses for t in record.turns] == [2, 1]
    card = build_card(record)
    assert [t.responses for t in card.raw_turns] == [2, 1]
    text = render_card_text(card)
    assert "responses per turn" in text.lower()
    assert "s1 turn 1 = 2 (split)" in text and "s1 turn 2 = 1" in text


# --- barge-in measurement (AC-28, AC-29) ----------------------------------------------------


def _bargein_turns(script: list, tmp_path: Path) -> list:
    raw = make_spec()
    raw["scenarios"][0]["user_turns"] = [
        {"text": "Tell me a story."},
        {"text": "Stop.", "interrupt_after_assistant_ms": 100},
    ]
    record = Harness(tmp_path, raw, script, [GOOD]).run()
    return [(t.turn_index, t.bargein_ms, t.bargein_status) for t in record.turns]


def _interrupted_reply(status: str) -> list:
    return [
        AudioDelta("A", 4800, 1000.4),
        TranscriptDelta("A", "Once upon", 1000.4),
        AudioDelta("A", 4800, 1000.5),
        ResponseDone("A", status, None, 1000.6),
        AudioDelta("B", 4800, 1001.5),
        TranscriptDelta("B", "Sure.", 1001.5),
        ResponseDone("B", "completed", None, 1001.6),
    ]


def test_ac29_cancelled_interruption_is_measured(tmp_path: Path) -> None:
    turns = _bargein_turns(_interrupted_reply("cancelled"), tmp_path)
    assert turns[1][2] == "measured"
    assert turns[1][1] is not None


def test_ac29_completed_interruption_is_not_measured(tmp_path: Path) -> None:
    turns = _bargein_turns(_interrupted_reply("completed"), tmp_path)
    assert turns[1][1:] == (None, "not measured")
