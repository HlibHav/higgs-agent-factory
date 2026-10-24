"""Turns a gate run record into an Eval Card (domain)."""

from factory.gate.cost import TOKEN_NOT_MEASURABLE, TokenCost, audio_cost, token_cost
from factory.gate.metrics import bargein_summary, ttfa_summary
from factory.gate.records import EvalCard, GateRunRecord, IhbenchRq
from factory.gate.verdict import decide_verdict
from factory.ports import Usage


def build_card(record: GateRunRecord, ihbench: IhbenchRq | None = None) -> EvalCard:
    """`ihbench=None` leaves RQ as None, which the card shows as "not available"."""
    verdict, failing = decide_verdict(record)
    ttfa = ttfa_summary(record.turns)
    bargein = bargein_summary(record.turns)
    in_min = record.input_audio_s / 60
    out_min = record.output_audio_s / 60
    audio = audio_cost(in_min, out_min)
    tokens = token_cost(record.usages)
    judged = [s for s in record.scenarios if s.judgment is not None]
    passed = sum(1 for s in judged if s.judgment and s.judgment.label == "PASS")
    total: Usage | None = None
    text: str | None = TOKEN_NOT_MEASURABLE
    if isinstance(tokens, TokenCost):
        total = Usage(tokens.input_tokens, tokens.cached_tokens, tokens.output_tokens)
        text = None
    return EvalCard(
        agent_id=record.agent_id,
        run_id=record.run_id,
        ended_at=record.ended_at,
        verdict=verdict,
        incomplete_cause=record.cause,
        cause_detail=record.cause_detail,
        scenarios=record.scenarios,
        scenarios_run=len(record.scenarios),
        pass_rate=passed / len(record.scenarios) if record.scenarios else None,
        failing_rubric_lines=failing,
        ihbench_rq=ihbench,
        ttfa_p50_ms=ttfa.p50_ms,
        ttfa_p95_ms=ttfa.p95_ms,
        ttfa_n=ttfa.n,
        ttfa_label=ttfa.label,
        bargein_p50_ms=bargein.p50_ms,
        bargein_tail_ms=bargein.max_ms,
        bargein_tail_kind="max",
        input_audio_minutes=in_min,
        output_audio_minutes=out_min,
        estimated_audio_cost_usd=audio.usd,
        estimated_audio_cost_label=audio.label,
        estimated_audio_cost_per_minute_usd=None,  # denominator is an open spec marker
        token_usage_total=total,
        token_cost_text=text,
        raw_turns=record.turns,
    )
