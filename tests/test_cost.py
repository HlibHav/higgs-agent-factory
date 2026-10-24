"""AC-30, AC-31, AC-32: estimated audio cost, token part, card text."""

import re
from datetime import UTC, datetime

from factory.gate.cost import (
    AUDIO_COST_LABEL,
    AUDIO_IN_USD_PER_MIN,
    AUDIO_OUT_USD_PER_MIN,
    TOKEN_NOT_MEASURABLE,
    audio_cost,
    token_cost,
)
from factory.gate.records import EvalCard
from factory.gate.render import render_card_text
from factory.ports import Usage


def _card(**kw) -> EvalCard:
    base = dict(
        agent_id="a1",
        run_id="r1",
        ended_at=datetime(2026, 10, 24, tzinfo=UTC),
        verdict="released",
        scenarios=[],
        raw_turns=[],
    )
    base.update(kw)
    return EvalCard(**base)


def test_ac30_audio_cost_formula_and_label():
    c = audio_cost(2.0, 1.5)
    assert c.usd == 2.0 * AUDIO_IN_USD_PER_MIN + 1.5 * AUDIO_OUT_USD_PER_MIN
    assert (c.input_min, c.output_min) == (2.0, 1.5)
    assert c.label == AUDIO_COST_LABEL == "estimated from Boson's published per-minute rates"


def test_ac30_f12_rates():
    assert (AUDIO_IN_USD_PER_MIN, AUDIO_OUT_USD_PER_MIN) == (0.0023, 0.014)


def test_ac30_card_text_shows_minutes_estimate_and_label():
    c = audio_cost(2.0, 1.5)
    text = render_card_text(
        _card(
            input_audio_minutes=2.0,
            output_audio_minutes=1.5,
            estimated_audio_cost_usd=c.usd,
            estimated_audio_cost_label=c.label,
        )
    )
    assert "2.00 min" in text and "1.50 min" in text
    assert AUDIO_COST_LABEL in text
    assert f"${c.usd:.4f}" in text


def test_ac31_missing_usage_gives_exact_text_and_no_token_amount():
    usages = [Usage(10, 0, 5), None, Usage(20, 4, 8)]
    assert token_cost(usages) == "not measurable"
    text = render_card_text(_card(token_cost_text=TOKEN_NOT_MEASURABLE, token_usage_total=None))
    assert TOKEN_NOT_MEASURABLE in text
    assert (
        TOKEN_NOT_MEASURABLE == "Billed token cost: not measurable, the API returns no usage (F2)"
    )
    # no dollar figure other than the audio estimate (none set here)
    assert "$" not in text


def test_ac31_all_usage_present_shows_counts_and_no_token_dollars():
    t = token_cost([Usage(10, 2, 5), Usage(20, 4, 8)])
    assert (t.input_tokens, t.cached_tokens, t.output_tokens) == (30, 6, 13)
    text = render_card_text(_card(token_usage_total=Usage(30, 6, 13)))
    assert "30" in text and "13" in text
    assert "$" not in text
    assert TOKEN_NOT_MEASURABLE not in text


def test_non_numeric_usage_counts_as_missing():
    assert token_cost([Usage(10, 0, 5), Usage("x", 0, 5)]) == "not measurable"  # type: ignore[arg-type]
    assert token_cost([Usage(10, 0, None)]) == "not measurable"  # type: ignore[arg-type]
    assert token_cost([Usage(True, 0, 5)]) == "not measurable"  # type: ignore[arg-type]
    assert token_cost([Usage(-1, 0, 5)]) == "not measurable"


def test_ac31_no_responses_is_not_measurable():
    assert token_cost([]) == "not measurable"


def test_ac32_no_amount_labelled_billed_actual_or_invoiced():
    c = audio_cost(2.0, 1.5)
    text = render_card_text(
        _card(
            estimated_audio_cost_usd=c.usd,
            estimated_audio_cost_label=c.label,
            token_cost_text=TOKEN_NOT_MEASURABLE,
        )
    )
    for line in text.splitlines():
        if re.search(r"billed|actual|invoiced", line, re.IGNORECASE):
            assert "$" not in line and line == TOKEN_NOT_MEASURABLE
    assert "$" in text  # the audio estimate is shown, labelled as an estimate


def test_card_text_verdict_word_and_rq_not_available():
    text = render_card_text(_card(verdict="rejected"))
    assert "rejected" in text
    assert "not available" in text
