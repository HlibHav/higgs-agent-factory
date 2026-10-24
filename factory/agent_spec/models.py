"""Agent Spec schema (domain). Pure pydantic models; no SDK, no I/O."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class AgentSpec(_Strict):
    id: str
    schema_version: Literal[1]
    source: TemplateSource | BriefSource = Field(discriminator="kind")
    role: str
    instructions: str
    voice: str
    output_modality: Literal["audio"]  # F6
    temperature: float | None = None
    max_output_tokens: int | None = None
    tools: list[Annotated[ClientTool | ServerWebSearch, Field(discriminator="kind")]] = Field(
        default_factory=list
    )
    turn_detection: ServerVad | None  # None = manual turns (F16, F24)
    scenarios: list[Scenario]
    budget: BudgetLimits


class SpecIssue(_Strict):
    field: str
    message: str
