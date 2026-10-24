"""AC-12, AC-13, AC-18 (verdict half), AC-19: the verdict comes from labels and completion only."""

from datetime import UTC, datetime

from factory.agent_spec.models import Rubric
from factory.gate.records import GateRunRecord, Judgment, ScenarioRecord, TurnRecord
from factory.gate.verdict import decide_verdict


def _rubric(tag: str) -> Rubric:
    return Rubric(
        pass_criteria=[f"{tag} pass"],
        partial_criteria=[f"{tag} partial"],
        fail_criteria=[f"{tag} fail"],
    )


def _scenario(sid: str, label: str | None) -> ScenarioRecord:
    judgment = (
        None if label is None else Judgment(label=label, rationale=f"r-{sid}", evidence=f"e-{sid}")
    )
    return ScenarioRecord(
        scenario_id=sid,
        title=sid,
        rubric=_rubric(sid),
        judgment=judgment,
        transcript="",
        tool_calls=[],
        expected_call_match=None,
        audio_source="synthesised",
    )


def _record(labels: list[str | None], cause=None, turns=None) -> GateRunRecord:
    return GateRunRecord(
        agent_id="a1",
        run_id="r1",
        ended_at=datetime(2026, 10, 24, tzinfo=UTC),
        scenarios=[_scenario(f"s{i}", lab) for i, lab in enumerate(labels)],
        turns=turns or [],
        usages=[],
        input_audio_s=0.0,
        output_audio_s=0.0,
        cause=cause,
        cause_detail=None,
    )


def test_ac12_partial_rejects_with_failing_lines():
    verdict, lines = decide_verdict(_record(["PASS", "PARTIAL", "PASS"]))
    assert verdict == "rejected"
    assert len(lines) == 1
    line = lines[0]
    assert line.scenario_id == "s1"
    assert line.label == "PARTIAL"
    assert line.rubric == _rubric("s1")
    assert line.rationale == "r-s1"
    assert line.evidence == "e-s1"


def test_ac12_fail_rejects():
    verdict, lines = decide_verdict(_record(["FAIL", "PASS"]))
    assert verdict == "rejected"
    assert [ln.label for ln in lines] == ["FAIL"]


def test_ac13_all_pass_releases():
    assert decide_verdict(_record(["PASS", "PASS", "PASS"])) == ("released", [])


def test_ac18_cause_makes_incomplete_even_if_labels_pass():
    verdict, lines = decide_verdict(_record(["PASS", None], cause="judge reply invalid"))
    assert verdict == "incomplete"
    assert lines == []


def test_ac18_cause_wins_over_failing_label():
    verdict, _ = decide_verdict(_record(["FAIL", None], cause="budget reached"))
    assert verdict == "incomplete"


def test_ac13_unjudged_scenario_without_cause_is_never_released():
    verdict, _ = decide_verdict(_record(["PASS", None]))
    assert verdict == "incomplete"


def test_ac13_empty_run_is_never_released():
    verdict, _ = decide_verdict(_record([]))
    assert verdict == "incomplete"


def test_ac19_slow_ttfa_does_not_change_verdict():
    slow = [TurnRecord("s0", 0, "scripted", 30_000.0, None, None)]
    assert decide_verdict(_record(["PASS", "PASS"], turns=slow))[0] == "released"
