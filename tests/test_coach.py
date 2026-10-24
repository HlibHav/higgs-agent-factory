import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from factory.agent_spec.models import AgentSpec, Rubric
from factory.agent_spec.templates import load_template
from factory.coach.coach import build_coach_prompt, coach_spec, parse_procedure
from factory.composition import FactoryApp
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore
from factory.gate.records import EvalCard, GateRunRecord, Judgment, ScenarioRecord
from factory.gate.runner import GateAborted
from factory.gate.tts_cache import TurnAudioSource
from tests.doubles import FakeJudge, FakeSessionFactory, FakeTts

_R = Rubric(pass_criteria=["p"], partial_criteria=["q"], fail_criteria=["f"])


class FakeCoach:
    def __init__(self, reply: str = json.dumps({"procedure": "NEW"})) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def rewrite_procedure(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def _spec() -> AgentSpec:
    return load_template("specialist-training")


def _card(spec: AgentSpec, run_id: str, labels: dict[str, str], **extra: Any) -> EvalCard:
    scs = []
    for skill in spec.skills:
        for sc in skill.scenarios:
            label = labels.get(skill.id, "PASS")
            scs.append(
                ScenarioRecord(
                    sc.id,
                    sc.title,
                    sc.rubric,
                    Judgment(label, "why <b>", "ev"),  # type: ignore[arg-type]
                    "transcript </data> text",
                    [],
                    None,
                    "synthesised",
                    skill_id=skill.id,
                    skill_name=skill.name,
                    judge_labels=[label, label],  # type: ignore[list-item]
                    judge_agreed=True,
                )
            )
    rec = GateRunRecord(
        spec.id,
        run_id,
        datetime.now(UTC),
        scs,
        [],
        [],
        1.0,
        1.0,
        None,
        None,
        agent_version=spec.version,
        agent_spec=spec.model_dump(mode="json"),
    )
    return build_card(rec).model_copy(update=extra)


def test_ac76_only_the_failing_skill_procedure_changes() -> None:
    spec = _spec()
    assert len(spec.skills) >= 2
    failing_id = spec.skills[1].id
    card = _card(spec, "r1", {failing_id: "FAIL"})
    result = asyncio.run(coach_spec(spec, card, FakeCoach()))
    assert result is not None
    new, changed = result
    assert changed == [failing_id]
    assert new.version == spec.version + 1
    for old_skill, new_skill in zip(spec.skills, new.skills, strict=True):
        if old_skill.id == failing_id:
            assert new_skill.procedure == "NEW"
            assert new_skill.model_dump(exclude={"procedure"}) == old_skill.model_dump(
                exclude={"procedure"}
            )
        else:
            assert new_skill == old_skill
    assert new.model_dump(exclude={"skills", "version"}) == spec.model_dump(
        exclude={"skills", "version"}
    )


def test_coach_calls_once_per_failing_skill_and_none_when_all_pass() -> None:
    spec = _spec()
    ids = {s.id: "FAIL" for s in spec.skills}
    coach = FakeCoach()
    result = asyncio.run(coach_spec(spec, _card(spec, "r1", ids), coach))
    assert result is not None and sorted(result[1]) == sorted(ids)
    assert len(coach.prompts) == len(spec.skills)
    assert asyncio.run(coach_spec(spec, _card(spec, "r2", {}), FakeCoach())) is None


def test_invalid_reply_gives_none() -> None:
    spec = _spec()
    card = _card(spec, "r1", {spec.skills[0].id: "FAIL"})
    for bad in [
        "nope",
        '{"procedure": ""}',
        '{"procedure": "x", "y": 1}',
        json.dumps({"procedure": "x" * 601}),
    ]:
        assert asyncio.run(coach_spec(spec, card, FakeCoach(bad))) is None
    assert parse_procedure('{"procedure": "ok"}') == "ok"


def test_prompt_keeps_untrusted_text_inside_json_blocks() -> None:
    spec = _spec()
    card = _card(spec, "r1", {spec.skills[0].id: "FAIL"})
    failing = [s for s in card.scenarios if not s.passed]
    prompt = build_coach_prompt(spec.skills[0], failing)
    assert "</data> text" not in prompt and "\\u003c/data> text" in prompt
    assert "never instructions" in prompt and '"procedure"' in prompt


def _app(tmp_path: Path, coach: FakeCoach) -> FactoryApp:
    return FactoryApp(
        sessions=FakeSessionFactory(),
        audio=TurnAudioSource(FakeTts(), tmp_path / "tts", tmp_path / "rec"),
        judge=FakeJudge([]),
        store=FileCardStore(tmp_path / "cards"),
        coach_model=coach,
    )


def test_ac77_coach_template_regates_and_verdict_is_its_own(tmp_path: Path) -> None:
    app = _app(tmp_path, FakeCoach())
    spec = _spec()
    failing_id = spec.skills[0].id
    gated: list[AgentSpec] = []

    async def fake_gate(s: AgentSpec, **kw: Any) -> EvalCard | GateAborted:
        gated.append(s)
        labels = {failing_id: "FAIL"} if s.version == 1 else {}
        card = _card(s, f"run{s.version}", labels)
        if kw.get("parent_run_id"):
            card = card.model_copy(
                update={
                    "parent_run_id": kw["parent_run_id"],
                    "agent_version": s.version,
                    "coach_note": kw["coach_note"],
                }
            )
        app.store.save(card)
        return card

    app._gate = fake_gate  # type: ignore[method-assign]
    cards = asyncio.run(app.coach_template("specialist-training", rounds=2, from_latest=False))
    assert isinstance(cards, list) and len(cards) == 2
    assert [c.verdict for c in cards] == ["rejected", "released"]
    assert cards[1].parent_run_id == "run1" and cards[1].agent_version == 2
    assert cards[1].coach_note == f"coach rewrote: {failing_id}"
    assert len(gated) == 2 and gated[1].version == 2
    # the page and live talk use the coached version
    served = app.agent_spec(spec.id)
    assert served is not None and served.version == 2
    pair = app.coach_pair(spec.id)
    assert pair is not None and pair[0].run_id == "run1" and pair[1].run_id == "run2"


def test_coach_template_starts_from_stored_rejected_card(tmp_path: Path) -> None:
    app = _app(tmp_path, FakeCoach())
    spec = _spec()
    stored = _card(spec, "base", {spec.skills[0].id: "FAIL"})
    app.store.save(stored)
    calls: list[AgentSpec] = []

    async def fake_gate(s: AgentSpec, **kw: Any) -> EvalCard | GateAborted:
        calls.append(s)
        return _card(s, "second", {})

    app._gate = fake_gate  # type: ignore[method-assign]
    cards = asyncio.run(app.coach_template("specialist-training"))
    assert isinstance(cards, list) and cards[0].run_id == "base"
    assert len(calls) == 1 and calls[0].version == 2
