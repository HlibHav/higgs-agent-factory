"""Gate run records and the Eval Card (domain). No SDK imports."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from factory.agent_spec.models import Rubric
from factory.ports import ToolCall, Usage

Label = Literal["PASS", "PARTIAL", "FAIL"]
Verdict = Literal["released", "rejected", "incomplete"]
Cause = Literal[
    "quota refused",
    "idle timeout",
    "concurrency limit",
    "budget reached",
    "judge reply invalid",
    "audio missing",
]


@dataclass(frozen=True)
class Judgment:
    label: Label
    rationale: str
    evidence: str


@dataclass(frozen=True)
class TurnRecord:
    scenario_id: str
    turn_index: int
    kind: Literal["scripted", "live"]
    ttfa_ms: float | None
    bargein_ms: float | None
    bargein_status: Literal["measured", "not measured"] | None
    responses: int = 1  # responses inside the turn's quiet window (AC-61)


@dataclass(frozen=True)
class ScenarioRecord:
    scenario_id: str
    title: str
    rubric: Rubric
    judgment: Judgment | None
    transcript: str
    tool_calls: list[ToolCall]
    expected_call_match: Literal["matched", "not matched"] | None
    audio_source: Literal["synthesised", "recorded"]
    # Diagnostics for an invalid judge reply (AC-62, AC-63). The raw reply is untrusted model
    # output kept as inert data: never parsed, rendered or used as rationale or evidence.
    judge_raw_reply: str | None = None
    judge_raw_truncated: bool = False
    transcript_chars: int | None = None
    skill_id: str = "main"
    skill_name: str = "Main"
    # AC-75: every valid label of the k judge calls; agreed is False when they differ or one
    # reply was invalid. A disagreed scenario never counts as PASS.
    judge_labels: list[Label] = field(default_factory=list)
    judge_agreed: bool | None = None

    @property
    def passed(self) -> bool:
        return (
            self.judgment is not None
            and self.judgment.label == "PASS"
            and self.judge_agreed is not False
        )


@dataclass(frozen=True)
class GateRunRecord:
    agent_id: str
    run_id: str
    ended_at: datetime
    scenarios: list[ScenarioRecord]
    turns: list[TurnRecord]
    usages: list[Usage | None]
    input_audio_s: float
    output_audio_s: float
    cause: Cause | None
    cause_detail: str | None
    agent_version: int = 1
    agent_spec: dict[str, Any] | None = None  # the spec that ran, so a coached version reloads


class SkillResult(BaseModel):
    """AC-74: one skill's share of a gate run."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    name: str
    scenarios_run: int
    passed: int
    pass_rate: float | None
    released: bool


class FailingScenario(BaseModel):
    """AC-12: one non-PASS scenario with the rubric lines it was judged against."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    label: Label
    rubric: Rubric
    rationale: str
    evidence: str
    skill_id: str = "main"
    judge_agreed: bool | None = None


class IhbenchRq(BaseModel):
    """AC-34: model-level IHBench result from Spec B."""

    model_config = ConfigDict(extra="forbid")

    rq_pass_rate: float
    label: str = "model-level, IHBench samples"
    source: str
    date: str


class EvalCard(BaseModel):
    """Every field of the spec's Eval Card table, plus the raw per-turn measurements."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    agent_id: str
    run_id: str
    ended_at: datetime
    verdict: Verdict
    incomplete_cause: Cause | None = None
    cause_detail: str | None = None
    scenarios: list[ScenarioRecord]
    scenarios_run: int = 0
    pass_rate: float | None = None
    failing_rubric_lines: list[FailingScenario] = []
    ihbench_rq: IhbenchRq | None = None  # None renders as "not available"
    ttfa_p50_ms: float | None = None
    ttfa_p95_ms: float | None = None
    ttfa_n: int = 0
    ttfa_label: str | None = None
    bargein_p50_ms: float | None = None
    bargein_tail_ms: float | None = None  # max or p95: open question (AC-29)
    bargein_tail_kind: Literal["max", "p95"] | None = None
    input_audio_minutes: float = 0.0
    output_audio_minutes: float = 0.0
    estimated_audio_cost_usd: float | None = None
    estimated_audio_cost_label: str | None = None
    estimated_audio_cost_per_minute_usd: float | None = None
    token_usage_total: Usage | None = None
    measured_token_cost_usd: float | None = None
    measured_token_cost_label: str | None = None
    token_cost_text: str | None = None  # AC-31 text when any response lacked usage
    raw_turns: list[TurnRecord]
    skills: list[SkillResult] = []
    judge_agreement_rate: float | None = None
    agent_version: int = 1
    parent_run_id: str | None = None  # the run the coach started from (AC-76)
    coach_note: str | None = None
    agent_spec: dict[str, Any] | None = None
