from datetime import UTC, datetime

from factory.agent_spec.models import Rubric
from factory.gate.card_builder import build_card
from factory.gate.diff import diff_cards, render_diff_text
from factory.gate.records import GateRunRecord, Judgment, ScenarioRecord

_R = Rubric(pass_criteria=["p"], partial_criteria=["q"], fail_criteria=["f"])


def _card(run_id: str, st6: str):
    scs = [
        ScenarioRecord(
            "st-1",
            "a",
            _R,
            Judgment("PASS", "r", "e"),
            "t",
            [],
            None,
            "synthesised",
            skill_id="identity-check",
            skill_name="Identity check",
            judge_labels=["PASS", "PASS"],
            judge_agreed=True,
        ),
        ScenarioRecord(
            "st-6",
            "b",
            _R,
            Judgment(st6, "r", "e"),
            "t",
            [],
            None,
            "synthesised",
            skill_id="scope-guard",
            skill_name="Scope guard",
            judge_labels=[st6, st6],
            judge_agreed=True,
        ),
    ]
    rec = GateRunRecord(
        "specialist-training", run_id, datetime.now(UTC), scs, [], [], 1.0, 1.0, None, None
    )
    return build_card(rec)


def test_ac78_diff_shows_label_skill_and_verdict_change() -> None:
    before, after = _card("r1", "PARTIAL"), _card("r2", "PASS")
    assert before.verdict == "rejected" and after.verdict == "released"
    d = diff_cards(before, after)
    assert (d.verdict.before, d.verdict.after) == ("rejected", "released")
    st6 = next(c for c in d.scenarios if c.key == "st-6")
    assert (st6.before, st6.after) == ("PARTIAL", "PASS")
    guard = next(c for c in d.skills if c.key == "scope-guard")
    assert (guard.before, guard.after) == ("0/1", "1/1")
    text = render_diff_text(d)
    assert "* st-6: PARTIAL -> PASS" in text and "* verdict: rejected -> released" in text
