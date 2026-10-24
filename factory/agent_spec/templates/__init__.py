"""Solution templates: complete Agent Specs loaded from JSON. Deterministic, no model call."""

import json
from importlib import resources
from typing import get_args

from factory.agent_spec.models import AgentSpec, TemplateId
from factory.agent_spec.validation import validate_agent_spec

TEMPLATE_IDS: tuple[str, ...] = get_args(TemplateId)


class TemplateNotAvailable(Exception):
    """The template id is unknown, or its card text is not in the repo yet."""


def load_template(template_id: str) -> AgentSpec:
    """Return a fresh, validated copy of the template (AC-3)."""
    if template_id not in TEMPLATE_IDS:
        raise TemplateNotAvailable(f"unknown template: {template_id!r}")
    resource = resources.files(__package__).joinpath(f"{template_id.replace('-', '_')}.json")
    if not resource.is_file():
        raise TemplateNotAvailable(f"card text pending for template: {template_id}")
    result = validate_agent_spec(json.loads(resource.read_text(encoding="utf-8")))
    if not isinstance(result, AgentSpec):
        fields = ", ".join(issue.field for issue in result)
        raise ValueError(f"template {template_id} is not a valid Agent Spec: {fields}")
    return result
