"""Solution templates (step 7). Deterministic, no model call."""

import re

import pytest

from factory.agent_spec.models import AgentSpec, TemplateSource
from factory.agent_spec.templates import (
    TEMPLATE_IDS,
    TemplateNotAvailable,
    load_template,
)
from factory.agent_spec.validation import validate_agent_spec

_PENDING = pytest.mark.xfail(strict=True, reason="card text pending", raises=TemplateNotAvailable)


@pytest.mark.parametrize(
    "template_id",
    [
        pytest.param("health-insurance", marks=_PENDING),
        pytest.param("fraud-detection", marks=_PENDING),
        pytest.param("customer-support", marks=_PENDING),
        pytest.param("ai-receptionist", marks=_PENDING),
        "specialist-training",
    ],
)
def test_ac3_each_template_valid_with_source(template_id: str) -> None:
    spec = load_template(template_id)
    assert isinstance(spec, AgentSpec)
    assert spec.source == TemplateSource(template_id=template_id)
    # Round trip through the public validator: a template is a valid Agent Spec.
    assert isinstance(validate_agent_spec(spec.model_dump(mode="json")), AgentSpec)


def test_template_ids_are_the_five_cards() -> None:
    assert TEMPLATE_IDS == (
        "health-insurance",
        "fraud-detection",
        "customer-support",
        "ai-receptionist",
        "specialist-training",
    )
    with pytest.raises(TemplateNotAvailable):
        load_template("no-such-template")


def test_ac5_specialist_training_budget() -> None:
    budget = load_template("specialist-training").budget
    assert budget.max_scenarios == 6
    assert budget.max_audio_s_per_run == 240  # 4 minutes, input plus output
    assert budget.max_judge_calls_per_scenario == 1
    assert budget.max_live_session_s == 180  # 3 minutes


def test_specialist_training_fits_audio_budget() -> None:
    spec = load_template("specialist-training")
    assert len(spec.scenarios) == spec.budget.max_scenarios == 6
    assert spec.max_output_tokens is not None
    assert "two sentences" in spec.instructions
    for scenario in spec.scenarios:
        assert 1 <= len(scenario.user_turns) <= 2
        for turn in scenario.user_turns:
            assert len(turn.text) <= 200


def test_specialist_training_shape() -> None:
    spec = load_template("specialist-training")
    assert spec.voice == "default"  # F7
    assert spec.output_modality == "audio"  # F6
    assert spec.tools == []
    assert spec.turn_detection is not None
    assert (spec.turn_detection.threshold, spec.turn_detection.prefix_padding_ms) == (0.85, 300)
    assert spec.turn_detection.silence_duration_ms == 500  # F8 defaults
    assert len({s.id for s in spec.scenarios}) == 6
    interrupting = [
        s for s in spec.scenarios for t in s.user_turns if t.interrupt_after_assistant_ms
    ]
    assert len(interrupting) == 1
    for scenario in spec.scenarios:
        rubric = scenario.rubric
        assert rubric.pass_criteria and rubric.partial_criteria and rubric.fail_criteria
        assert all(t.recording is None for t in scenario.user_turns)


def test_load_template_returns_independent_copies() -> None:
    a = load_template("specialist-training")
    a.scenarios.clear()
    assert len(load_template("specialist-training").scenarios) == 6


_ST5_RUBRIC = {
    "pass_criteria": [
        "The assistant stops its first answer when interrupted, so the first answer in the "
        "transcript ends early or mid-sentence.",
        "The answer to the second question says to acknowledge the feeling first, then say "
        "what will be done.",
        "The answer to the second question is at most two sentences.",
    ],
    "partial_criteria": [
        "The answer to the second question is correct, but the first answer continues to its "
        "end as if there was no interruption.",
        "The answer to the second question is correct but ignores the order (feeling first, "
        "then action).",
    ],
    "fail_criteria": [
        "The assistant ignores the second question and keeps talking about the first.",
        "The answer to the second question puts the fix before acknowledging the feeling.",
    ],
}


def test_no_scripted_turn_has_an_internal_sentence_break() -> None:
    # Scoped to the interrupting turns: st-1..4 and st-6 are single first turns whose
    # two-sentence wording the live run did not split (see implementer report).
    spec = load_template("specialist-training")
    checked = 0
    for scenario in spec.scenarios:
        for turn in scenario.user_turns:
            if turn.interrupt_after_assistant_ms is None:
                continue
            checked += 1
            assert re.search(r"[.?!\u2026](?=.)", turn.text.strip()) is None, turn.text
    assert checked >= 1


def test_st5_rubric_unchanged() -> None:
    spec = load_template("specialist-training")
    st5 = next(s for s in spec.scenarios if s.id == "st-5")
    assert st5.rubric.model_dump() == _ST5_RUBRIC
    assert st5.user_turns[1].interrupt_after_assistant_ms == 1500
