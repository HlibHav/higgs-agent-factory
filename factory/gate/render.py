"""Plain-text Eval Card (domain). Verdict as a word; no amount next to billed/actual/invoiced."""

from factory.gate.records import EvalCard


def _ms(v: float | None) -> str:
    return "not measured" if v is None else f"{v:.0f} ms"


def render_card_text(card: EvalCard) -> str:
    lines = [
        f"Agent {card.agent_id}, run {card.run_id}, {card.ended_at.isoformat()}",
        f"Verdict: {card.verdict}",
    ]
    if card.verdict == "incomplete":
        lines.append(f"Incomplete cause: {card.incomplete_cause or 'unknown'}")
        if card.cause_detail:
            lines.append(f"Detail: {card.cause_detail}")
    rate = "n/a" if card.pass_rate is None else f"{card.pass_rate * 100:.0f}%"
    lines.append(f"Scenarios run: {card.scenarios_run}, pass rate: {rate}")
    for f in card.failing_rubric_lines:
        lines.append(f"Failing scenario {f.scenario_id}: {f.label}")
        lines.append(f"  Pass: {'; '.join(f.rubric.pass_criteria)}")
        lines.append(f"  Partial: {'; '.join(f.rubric.partial_criteria)}")
        lines.append(f"  Fail: {'; '.join(f.rubric.fail_criteria)}")
        lines.append(f"  Rationale: {f.rationale}")
        lines.append(f"  Evidence: {f.evidence}")
    if card.ihbench_rq is None:
        lines.append("IHBench RQ: not available")
    else:
        rq = card.ihbench_rq
        lines.append(
            f"IHBench RQ: {rq.rq_pass_rate * 100:.0f}% ({rq.label}; {rq.source}, {rq.date})"
        )
    lines.append(
        f"TTFA p50 {_ms(card.ttfa_p50_ms)}, p95 {_ms(card.ttfa_p95_ms)}, n = {card.ttfa_n}"
        f" ({card.ttfa_label or ''})"
    )
    if card.bargein_tail_ms is None:
        lines.append("Barge-in stop time: not measured")
    else:
        lines.append(
            f"Barge-in stop time p50 {_ms(card.bargein_p50_ms)}, "
            f"{card.bargein_tail_kind} {_ms(card.bargein_tail_ms)}"
        )
    lines.append(
        f"Audio: {card.input_audio_minutes:.2f} min in, {card.output_audio_minutes:.2f} min out"
    )
    if card.estimated_audio_cost_usd is not None:
        lines.append(
            f"Estimated audio cost: ${card.estimated_audio_cost_usd:.4f}"
            f" ({card.estimated_audio_cost_label})"
        )
    if card.token_cost_text:
        lines.append(card.token_cost_text)
    elif card.token_usage_total is not None:
        u = card.token_usage_total
        lines.append(
            f"Tokens reported: {u.input_tokens} input, {u.cached_tokens} cached, "
            f"{u.output_tokens} output"
        )
    return "\n".join(lines)
