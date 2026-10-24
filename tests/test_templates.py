"""Solution templates (step 7). Deterministic, no model call."""

import json
import re

import pytest

from factory.agent_spec.models import AgentSpec, TemplateSource
from factory.agent_spec.templates import (
    TEMPLATE_IDS,
    TemplateNotAvailable,
    load_template,
)
from factory.agent_spec.validation import validate_agent_spec

_TOOL_TEMPLATES = ["health-insurance", "fraud-detection", "customer-support", "ai-receptionist"]


@pytest.mark.parametrize("template_id", [*_TOOL_TEMPLATES, "specialist-training"])
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
    assert budget.max_judge_calls_per_scenario == 2  # AC-75: judge agreement
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
        "The answer to the second question says to acknowledge the feeling first, then say "
        "what will be done.",
        "The answer to the second question is at most two sentences.",
    ],
    "partial_criteria": [
        "The answer to the second question is correct but ignores the order (feeling first, "
        "then action).",
    ],
    "fail_criteria": [
        "The assistant ignores the second question and keeps talking about the first.",
        "The answer to the second question puts the fix before acknowledging the feeling.",
    ],
}


_UNDECIDABLE = re.compile(
    r"cut off|mid-sentence|ends early|stops its first answer|continues to its end", re.I
)


def test_no_criterion_asks_judge_to_see_a_cut_off() -> None:
    # F27: the judge sees text, not audio, so it cannot decide whether an answer was cut off.
    spec = load_template("specialist-training")
    for scenario in spec.scenarios:
        rubric = scenario.rubric
        for line in [*rubric.pass_criteria, *rubric.partial_criteria, *rubric.fail_criteria]:
            assert not _UNDECIDABLE.search(line), (scenario.id, line)


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


@pytest.mark.parametrize("template_id", _TOOL_TEMPLATES)
def test_tool_template_shape_and_budget(template_id: str) -> None:
    spec = load_template(template_id)
    budget = spec.budget
    assert (budget.max_scenarios, budget.max_audio_s_per_run) == (6, 240)
    assert (budget.max_judge_calls_per_scenario, budget.max_live_session_s) == (1, 180)
    assert len(spec.scenarios) == budget.max_scenarios
    assert len({s.id for s in spec.scenarios}) == 6
    assert spec.voice == "default"  # F7
    assert spec.output_modality == "audio"  # F6
    assert spec.max_output_tokens is not None
    assert "two sentences" in spec.instructions
    assert spec.tools
    assert all(tool.kind == "client" for tool in spec.tools)  # mocks only, no side effects
    assert spec.turn_detection is not None
    assert (spec.turn_detection.threshold, spec.turn_detection.prefix_padding_ms) == (0.85, 300)
    assert spec.turn_detection.silence_duration_ms == 500  # F8 defaults


@pytest.mark.parametrize("template_id", _TOOL_TEMPLATES)
def test_tool_template_scenarios_are_speakable_and_decidable(template_id: str) -> None:
    spec = load_template(template_id)
    tool_names = {tool.name for tool in spec.tools}
    assert len(tool_names) == len(spec.tools)
    for scenario in spec.scenarios:
        assert 1 <= len(scenario.user_turns) <= 2
        for turn in scenario.user_turns:
            assert len(turn.text) <= 200  # audio budget
            assert turn.recording is None  # synthesised by TTS 3
            assert turn.interrupt_after_assistant_ms is None  # F27: no barge-in judging here
            assert not re.search(r"[\d{}\[\]<>]", turn.text), turn.text  # plain speakable words
        rubric = scenario.rubric
        assert rubric.pass_criteria and rubric.partial_criteria and rubric.fail_criteria
        for line in [*rubric.pass_criteria, *rubric.partial_criteria, *rubric.fail_criteria]:
            assert not _UNDECIDABLE.search(line), (scenario.id, line)  # F27
        if scenario.expected_tool_call is not None:
            assert scenario.expected_tool_call.name in tool_names, scenario.id


@pytest.mark.parametrize("template_id", _TOOL_TEMPLATES)
def test_tool_template_mocks_have_no_side_effects(template_id: str) -> None:
    spec = load_template(template_id)
    for tool in spec.tools:
        assert tool.kind == "client"
        for output in [tool.mock.default_output, *(c.output for c in tool.mock.by_argument)]:
            json.loads(output)  # a mock answers with a fixed JSON document
        assert tool.parameters["type"] == "object"
        required = set(tool.parameters.get("required", []))
        assert required <= set(tool.parameters["properties"]), tool.name
        for case in tool.mock.by_argument:
            assert set(case.when) <= set(tool.parameters["properties"]), tool.name
