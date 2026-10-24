"""Agent Spec validation: raw mapping in, `AgentSpec` or field-named issues out."""

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from factory.agent_spec.models import AgentSpec, SpecIssue


def _tool_name_at(raw: Mapping[str, Any], index: Any) -> str | None:
    tools = raw.get("tools")
    if isinstance(tools, list) and isinstance(index, int) and 0 <= index < len(tools):
        tool = tools[index]
        if isinstance(tool, Mapping) and isinstance(tool.get("name"), str):
            return tool["name"]
    return None


def _field_from_loc(raw: Mapping[str, Any], loc: tuple[Any, ...]) -> str:
    # Drop pydantic's union-branch tags ("client", "template", ...) that follow a list index
    # or "source"; they are not part of the user's data path.
    parts: list[Any] = []
    for i, part in enumerate(loc):
        if isinstance(part, str) and part in {"client", "server", "template", "brief"}:
            if i > 0 and (isinstance(loc[i - 1], int) or loc[i - 1] == "source"):
                continue
        parts.append(part)
    # `tools.<index>...` becomes `tools.<name>...` so AC-7 can name the tool.
    if len(parts) >= 2 and parts[0] == "tools":
        name = _tool_name_at(raw, parts[1])
        if name is not None:
            parts[1] = name
    return ".".join(str(p) for p in parts)


def _recording_issues(spec: AgentSpec) -> list[SpecIssue]:
    issues: list[SpecIssue] = []
    for si, scenario in enumerate(spec.scenarios):
        for ti, turn in enumerate(scenario.user_turns):
            if turn.recording is None:
                continue
            field = f"scenarios.{si}.user_turns.{ti}.recording"
            if spec.source.kind == "brief":
                issues.append(SpecIssue(field=field, message="recordings are not allowed here"))
                continue
            path = PurePosixPath(turn.recording)
            bare = (
                len(path.parts) == 1
                and path.name == turn.recording
                and turn.recording not in {"", ".", ".."}
                and "\\" not in turn.recording
            )
            if not bare:
                issues.append(SpecIssue(field=field, message="recording must be a bare filename"))
    return issues


def validate_agent_spec(raw: Mapping[str, Any]) -> AgentSpec | list[SpecIssue]:
    try:
        spec = AgentSpec.model_validate(dict(raw))
    except ValidationError as exc:
        return [
            SpecIssue(field=_field_from_loc(raw, tuple(err["loc"])), message=err["msg"])
            for err in exc.errors()
        ]
    issues = _recording_issues(spec)
    return issues or spec
