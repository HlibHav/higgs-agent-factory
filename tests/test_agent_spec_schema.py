"""Agent Spec schema: AC-6, AC-7 and the recording-path rule."""

import copy

from factory.agent_spec.models import AgentSpec, SpecIssue
from factory.agent_spec.validation import validate_agent_spec
from tests.doubles import make_spec


def _issues(raw: dict) -> list[SpecIssue]:
    result = validate_agent_spec(raw)
    assert isinstance(result, list), "expected validation issues"
    return result


def _client_tool() -> dict:
    return {
        "kind": "client",
        "name": "lookup_policy",
        "description": "Find a policy",
        "parameters": {"type": "object", "properties": {}},
        "mock": {"default_output": "{}", "by_argument": []},
    }


def test_valid_spec_passes() -> None:
    assert isinstance(validate_agent_spec(make_spec()), AgentSpec)


def test_ac6_idle_timeout_ms_rejected() -> None:
    raw = make_spec(
        turn_detection={
            "threshold": 0.85,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500,
            "idle_timeout_ms": 1000,  # F8: rejected by the server
        }
    )
    assert "turn_detection.idle_timeout_ms" in [i.field for i in _issues(raw)]


def test_ac7_client_tool_without_mock() -> None:
    tool = _client_tool()
    del tool["mock"]
    issues = _issues(make_spec(tools=[tool]))
    assert "tools.lookup_policy.mock" in [i.field for i in issues]


def test_client_tool_with_mock_is_valid() -> None:
    assert isinstance(validate_agent_spec(make_spec(tools=[_client_tool()])), AgentSpec)


def test_server_web_search_needs_no_mock() -> None:
    raw = make_spec(tools=[{"kind": "server", "name": "web_search"}])
    assert isinstance(validate_agent_spec(raw), AgentSpec)


def test_missing_budget_names_field() -> None:
    raw = make_spec()
    del raw["budget"]
    assert "budget" in [i.field for i in _issues(raw)]


def test_unknown_field_rejected() -> None:
    assert "surprise" in [i.field for i in _issues(make_spec(surprise=1))]


def test_recording_path_must_stay_in_recordings_dir() -> None:
    def spec_with_recording(recording: str, source: dict | None = None) -> dict:
        raw = copy.deepcopy(make_spec())
        raw["scenarios"][0]["user_turns"][0]["recording"] = recording
        if source is not None:
            raw["source"] = source
        return raw

    # a bare filename on a template spec is fine
    assert isinstance(validate_agent_spec(spec_with_recording("turn1.wav")), AgentSpec)

    for bad in ("../x.wav", "a/b.wav", "/etc/passwd", ".."):
        fields = [i.field for i in _issues(spec_with_recording(bad))]
        assert "scenarios.0.user_turns.0.recording" in fields, bad

    # any recording on a brief-sourced spec is rejected
    brief = {"kind": "brief", "text": "a pirate"}
    fields = [i.field for i in _issues(spec_with_recording("turn1.wav", brief))]
    assert "scenarios.0.user_turns.0.recording" in fields
