"""Agent Spec schema (domain). Pure pydantic models; no SDK, no I/O."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


TemplateId = Literal[
    "health-insurance",
    "fraud-detection",
    "customer-support",
    "ai-receptionist",
    "specialist-training",
]
UserVoice = Literal["chloe", "eleanor", "jake", "marcus", "nora", "oliver"]  # F22


class TemplateSource(_Strict):
    kind: Literal["template"] = "template"
    template_id: TemplateId


class BriefSource(_Strict):
    kind: Literal["brief"] = "brief"
    text: str


class ArgCase(_Strict):
    when: dict[str, Any]
    output: str


class MockBehaviour(_Strict):
    default_output: str
    by_argument: list[ArgCase] = Field(default_factory=list)


class ClientTool(_Strict):
    kind: Literal["client"] = "client"
    name: str
    description: str
    parameters: dict[str, Any]
    mock: MockBehaviour


class ServerWebSearch(_Strict):
    kind: Literal["server"] = "server"
    name: Literal["web_search"] = "web_search"  # F10


class ServerVad(_Strict):
    # F8: idle_timeout_ms is rejected by the server, so the field does not exist here.
    threshold: float
    prefix_padding_ms: int
    silence_duration_ms: int


class UserTurn(_Strict):
    text: str
    recording: str | None = None
    interrupt_after_assistant_ms: int | None = None


class Rubric(_Strict):
    pass_criteria: list[str]
    partial_criteria: list[str]
    fail_criteria: list[str]


class ExpectedCall(_Strict):
    """AC-23: a tool name and the argument values that must have been observed."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Scenario(_Strict):
    id: str
    title: str
    user_voice: UserVoice
    user_turns: list[UserTurn] = Field(min_length=1)
    expected_tool_call: ExpectedCall | None = None
    rubric: Rubric


class BudgetLimits(_Strict):
    max_scenarios: int
    max_audio_s_per_run: float
    max_judge_calls_per_scenario: int
    max_live_session_s: float


Tool = Annotated[ClientTool | ServerWebSearch, Field(discriminator="kind")]


class Skill(_Strict):
    """One unit of agent behaviour: its procedure, its tools and the scenarios that test it."""

    id: str
    name: str
    purpose: str
    procedure: str
    tools: list[Tool] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(min_length=1)  # AC-70: no vacuous skill


def _lift_v1(data: Any) -> Any:
    """AC-72: a flat schema-1 mapping becomes a persona with one skill."""
    if not isinstance(data, dict) or "skills" in data or "instructions" not in data:
        return data
    lifted = dict(data)
    lifted["schema_version"] = 2
    lifted["persona"] = lifted.pop("instructions")
    lifted["skills"] = [
        {
            "id": "main",
            "name": "Main",
            "purpose": str(lifted.get("role", "")),
            "procedure": "",
            "tools": lifted.pop("tools", []),
            "scenarios": lifted.pop("scenarios", []),
        }
    ]
    return lifted


class AgentSpec(_Strict):
    id: str
    schema_version: Literal[2]
    version: int = 1  # agent version; the coach increments it (AC-76)
    source: TemplateSource | BriefSource = Field(discriminator="kind")
    role: str
    persona: str
    voice: str
    output_modality: Literal["audio"]  # F6
    temperature: float | None = None
    max_output_tokens: int | None = None
    skills: list[Skill] = Field(min_length=1)
    turn_detection: ServerVad | None  # None = manual turns (F16, F24)
    budget: BudgetLimits

    @model_validator(mode="before")
    @classmethod
    def _accept_v1(cls, data: Any) -> Any:
        return _lift_v1(data)

    @model_validator(mode="after")
    def _unique_names(self) -> "AgentSpec":
        tools = [t.name for s in self.skills for t in s.tools]
        dup_tools = sorted({n for n in tools if tools.count(n) > 1})
        if dup_tools:
            raise ValueError(f"tool names must be unique across skills: {', '.join(dup_tools)}")
        ids = [sc.id for s in self.skills for sc in s.scenarios]
        dup_ids = sorted({i for i in ids if ids.count(i) > 1})
        if dup_ids:
            raise ValueError(f"scenario ids must be unique across skills: {', '.join(dup_ids)}")
        skill_ids = [s.id for s in self.skills]
        if len(set(skill_ids)) != len(skill_ids):
            raise ValueError("skill ids must be unique")
        return self

    # Derived views (AC-71). Plain properties, so they stay out of dumps and the JSON schema.
    @property
    def instructions(self) -> str:
        parts = [self.persona]
        for skill in self.skills:
            if skill.procedure.strip():
                parts.append(f"SKILL: {skill.name}\nPurpose: {skill.purpose}\n{skill.procedure}")
        return "\n\n".join(parts)

    @property
    def tools(self) -> list[ClientTool | ServerWebSearch]:
        return [t for s in self.skills for t in s.tools]

    @property
    def scenarios(self) -> list[Scenario]:
        return [sc for s in self.skills for sc in s.scenarios]

    def with_scenarios(self, scenarios: list[Scenario]) -> "AgentSpec":
        """A copy whose skills keep only the given scenarios (unvalidated, for runs)."""
        skills = []
        for skill in self.skills:
            own = {sc.id for sc in skill.scenarios}
            kept = [sc for sc in scenarios if sc.id in own]
            if kept:
                skills.append(skill.model_copy(update={"scenarios": kept}))
        return self.model_copy(update={"skills": skills})

    def skill_of(self, scenario_id: str) -> Skill | None:
        return next(
            (s for s in self.skills if any(sc.id == scenario_id for sc in s.scenarios)), None
        )


class SpecIssue(_Strict):
    field: str
    message: str
