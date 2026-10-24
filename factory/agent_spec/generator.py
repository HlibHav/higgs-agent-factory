"""Brief -> Agent Spec generator (service). Receives a `BriefModel` port; imports no SDK."""

import json
from typing import Any

from factory.agent_spec.models import AgentSpec, BriefSource, SpecIssue
from factory.agent_spec.validation import validate_agent_spec
from factory.ports import BriefModel

MAX_BRIEF_CHARS = 1000  # AC-2


class BriefTooLong(Exception):
    """The brief exceeds the cap. Raised before any model call (AC-2)."""

    def __init__(self, length: int) -> None:
        super().__init__(
            f"The brief has {length:,} characters; the limit is {MAX_BRIEF_CHARS:,} characters."
        )
        self.length = length


def _reply_issue(message: str) -> list[SpecIssue]:
    return [SpecIssue(field="model_reply", message=message)]


async def generate_from_brief(brief: str, model: BriefModel) -> AgentSpec | list[SpecIssue]:
    """Ask the model for a draft and validate it (AC-1).

    The model's reply is untrusted: it must be one strict JSON object, and `source` is set here,
    never taken from the reply.
    """
    if len(brief) > MAX_BRIEF_CHARS:
        raise BriefTooLong(len(brief))
    reply = await model.draft_spec(brief)
    try:
        raw: Any = json.loads(reply)
    except ValueError:
        return _reply_issue("the model reply is not valid JSON")
    if not isinstance(raw, dict):
        return _reply_issue("the model reply is not a JSON object")
    raw["source"] = BriefSource(text=brief).model_dump(mode="json")
    return validate_agent_spec(raw)
