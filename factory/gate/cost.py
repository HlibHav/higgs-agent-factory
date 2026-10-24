"""Cost figures (domain). Audio cost is an estimate; token cost is never given in dollars here."""

from dataclasses import dataclass
from typing import Literal

from factory.ports import Usage

# F12 price table (docs/boson-protocol.md).
AUDIO_IN_USD_PER_MIN = 0.0023  # F12
AUDIO_OUT_USD_PER_MIN = 0.014  # F12
# Token rates are kept for the measured token cost (step 21b), which waits on whether
# `input_tokens` includes `cached_tokens` (UNVERIFIED). Nothing here uses them yet.
INPUT_USD_PER_M = 0.75  # F12
CACHED_USD_PER_M = 0.25  # F12
OUTPUT_USD_PER_M = 4.50  # F12

AUDIO_COST_LABEL = "estimated from Boson's published per-minute rates"
# F2: the docs say the API returns no usage; AC-31 fixes this phrasing (docs/CLAIMS.md).
TOKEN_NOT_MEASURABLE = "Billed token cost: not measurable, the API returns no usage (F2)"


@dataclass(frozen=True)
class AudioCost:
    input_min: float
    output_min: float
    usd: float
    label: str


@dataclass(frozen=True)
class TokenCost:
    """Token counts summed over the run. No dollar figure: see the module note on step 21b."""

    input_tokens: int
    cached_tokens: int
    output_tokens: int


def audio_cost(input_min: float, output_min: float) -> AudioCost:
    usd = input_min * AUDIO_IN_USD_PER_MIN + output_min * AUDIO_OUT_USD_PER_MIN
    return AudioCost(input_min, output_min, usd, AUDIO_COST_LABEL)


def _is_count(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def token_cost(usages: list[Usage | None]) -> TokenCost | Literal["not measurable"]:
    """Missing or non-numeric usage on any response (or no responses) is not measurable."""
    if not usages:
        return "not measurable"
    for u in usages:
        if u is None or not (
            _is_count(u.input_tokens) and _is_count(u.cached_tokens) and _is_count(u.output_tokens)
        ):
            return "not measurable"
    return TokenCost(
        sum(u.input_tokens for u in usages if u),
        sum(u.cached_tokens for u in usages if u),
        sum(u.output_tokens for u in usages if u),
    )
