"""Agent Spec validation: raw mapping in, `AgentSpec` or field-named issues out."""

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from factory.agent_spec.models import AgentSpec, SpecIssue


def _named(items: Any, index: Any, key: str) -> str | None:
    if isinstance(items, list) and isinstance(index, int) and 0 <= index < len(items):
        item = items[index]
        if isinstance(item, Mapping) and isinstance(item.get(key), str):
            return str(item[key])
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
    flat = "skills" not in raw and "instructions" in raw
    if flat and len(parts) >= 2 and parts[0] == "skills" and parts[1] == 0:
        # A schema-1 spec was lifted into one skill (AC-72); report its own paths.
        parts = parts[2:]
        if parts and parts[0] == "persona":
            parts[0] = "instructions"
        tools = raw.get("tools")
    elif len(parts) >= 2 and parts[0] == "skills":
        skills = raw.get("skills")
        tools = None
        if isinstance(skills, list) and isinstance(parts[1], int) and 0 <= parts[1] < len(skills):
            skill = skills[parts[1]]
            tools = skill.get("tools") if isinstance(skill, Mapping) else None
        name = _named(skills, parts[1], "id")
        if name is not None:
            parts[1] = name
        prefix, parts = parts[:2], parts[2:]
        if len(parts) >= 2 and parts[0] == "tools":
            tool_name = _named(tools, parts[1], "name")
            if tool_name is not None:
                parts[1] = tool_name
        return ".".join(str(p) for p in prefix + parts)
    else:
        tools = raw.get("tools")
    # `tools.<index>...` becomes `tools.<name>...` so AC-7 can name the tool.
    if len(parts) >= 2 and parts[0] == "tools":
        name = _named(tools, parts[1], "name")
        if name is not None:
            parts[1] = name
    return ".".join(str(p) for p in parts) or "spec"


def _recording_issues(spec: AgentSpec, flat: bool) -> list[SpecIssue]:
    issues: list[SpecIssue] = []
    for si, scenario in enumerate(spec.scenarios):
        for ti, turn in enumerate(scenario.user_turns):
            if turn.recording is None:
                continue
            skill = spec.skill_of(scenario.id)
            where = (
                f"skills.{skill.id}.scenarios.{scenario.id}"
                if skill and not flat
                else f"scenarios.{si}"
            )
            field = f"{where}.user_turns.{ti}.recording"
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
    issues = _recording_issues(spec, "skills" not in raw and "instructions" in raw)
    return issues or spec
