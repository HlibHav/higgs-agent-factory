"""AC-33: two runs, two cards, nothing overwritten. Builder fills every Eval Card field."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factory.agent_spec.models import Rubric
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore, new_run_id
from factory.gate.cost import AUDIO_COST_LABEL, AUDIO_IN_USD_PER_MIN, TOKEN_NOT_MEASURABLE
from factory.gate.metrics import TTFA_LABEL
from factory.gate.records import GateRunRecord, Judgment, ScenarioRecord, TurnRecord
from factory.ports import ToolCall, Usage

_RUBRIC = Rubric(pass_criteria=["p"], partial_criteria=["q"], fail_criteria=["f"])


def _record(run_id="r1", label="PASS", usages=None, cause=None) -> GateRunRecord:
    sc = ScenarioRecord(
        scenario_id="s0",
        title="t",
        rubric=_RUBRIC,
        judgment=Judgment(label=label, rationale="why", evidence="quote"),
        transcript="hello",
        tool_calls=[ToolCall("c1", "lookup", {"q": 1}, "client", 1.5)],
        expected_call_match="matched",
        audio_source="synthesised",
    )
    turns = [
        TurnRecord("s0", 0, "scripted", 100.0, None, None),
        TurnRecord("s0", 1, "scripted", 300.0, None, None),
        TurnRecord("s0", 2, "live", 5000.0, None, None),
        TurnRecord("s0", 3, "scripted", None, 400.0, "measured"),
        TurnRecord("s0", 4, "scripted", None, None, "not measured"),
    ]
    return GateRunRecord(
        agent_id="a1",
        run_id=run_id,
        ended_at=datetime(2026, 10, 24, 12, 0, tzinfo=UTC),
        scenarios=[sc],
        turns=turns,
        usages=[Usage(10, 0, 5)] if usages is None else usages,
        input_audio_s=120.0,
        output_audio_s=90.0,
        cause=cause,
        cause_detail=None,
    )


def test_ac33_builder_fills_fields():
    card = build_card(_record())
    assert card.verdict == "released" and card.pass_rate == 1.0 and card.scenarios_run == 1
    assert (card.ttfa_p50_ms, card.ttfa_p95_ms, card.ttfa_n) == (100.0, 300.0, 2)
    assert card.ttfa_label == TTFA_LABEL
    assert (card.bargein_p50_ms, card.bargein_tail_ms, card.bargein_tail_kind) == (
        400.0,
        400.0,
        "max",
    )
    assert (card.input_audio_minutes, card.output_audio_minutes) == (2.0, 1.5)
    assert card.estimated_audio_cost_usd == pytest.approx(2.0 * AUDIO_IN_USD_PER_MIN + 1.5 * 0.014)
    assert card.estimated_audio_cost_label == AUDIO_COST_LABEL
    assert card.estimated_audio_cost_per_minute_usd is None
    assert card.token_usage_total == Usage(10, 0, 5)
    assert card.measured_token_cost_usd is None and card.token_cost_text is None
    assert card.ihbench_rq is None
    assert len(card.raw_turns) == 5


def test_ac31_builder_missing_usage():
    card = build_card(_record(usages=[Usage(1, 0, 1), None]))
    assert card.token_cost_text == TOKEN_NOT_MEASURABLE
    assert card.token_usage_total is None


def test_ac12_builder_rejected_carries_failing_lines():
    card = build_card(_record(label="PARTIAL"))
    assert card.verdict == "rejected" and card.pass_rate == 0.0
    assert card.failing_rubric_lines[0].rationale == "why"
    assert card.failing_rubric_lines[0].rubric == _RUBRIC


def test_ac18_builder_incomplete_carries_cause():
    card = build_card(_record(cause="idle timeout"))
    assert card.verdict == "incomplete" and card.incomplete_cause == "idle timeout"


def test_ac33_two_runs_two_cards(tmp_path: Path):
    store = FileCardStore(tmp_path)
    p1 = store.save(build_card(_record(run_id="r1")))
    p2 = store.save(build_card(_record(run_id="r2")))
    assert p1 != p2 and p1.exists() and p2.exists()
    assert p1 == tmp_path / "a1" / "r1.json"
    assert not (tmp_path / "a1" / "r1.json.tmp").exists()


def test_ac33_never_overwrites(tmp_path: Path):
    store = FileCardStore(tmp_path)
    store.save(build_card(_record(run_id="r1")))
    with pytest.raises(FileExistsError):
        store.save(build_card(_record(run_id="r1", label="FAIL")))
    assert store.latest("a1").verdict == "released"


def test_ac33_roundtrip_keeps_raw_records(tmp_path: Path):
    store = FileCardStore(tmp_path)
    card = build_card(_record())
    store.save(card)
    back = store.latest("a1")
    assert back == card
    assert back.raw_turns[0].ttfa_ms == 100.0


def test_latest_none_and_picks_newest(tmp_path: Path):
    store = FileCardStore(tmp_path)
    assert store.latest("a1") is None
    older = build_card(_record(run_id="20261024T100000Z-aaaaaaaa"))
    newer = build_card(_record(run_id="20261024T110000Z-bbbbbbbb"))
    store.save(newer)
    store.save(older)
    assert store.latest("a1").run_id == "20261024T110000Z-bbbbbbbb"


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".", "..", "a\\b"])
def test_ids_cannot_escape_root(tmp_path: Path, bad: str):
    store = FileCardStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(build_card(_record(run_id=bad)))
    with pytest.raises(ValueError):
        store.latest(bad)


def test_same_second_runs_distinct_ids():
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)
    a, b = new_run_id(now), new_run_id(now)
    assert a != b
    assert re.fullmatch(r"20261024T120000Z-[0-9a-f]{8}", a)


def test_card_roundtrip_keeps_responses(tmp_path: Path):
    record = _record()
    record.turns[0] = TurnRecord("s0", 0, "scripted", 100.0, None, None, responses=2)
    store = FileCardStore(tmp_path)
    store.save(build_card(record))
    back = store.latest("a1")
    assert back is not None and back.raw_turns[0].responses == 2
