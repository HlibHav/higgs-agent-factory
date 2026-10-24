"""TTFA and barge-in aggregates (domain)."""

import math
from dataclasses import dataclass

from factory.gate.records import TurnRecord

# F8: the client stops at the last speech chunk; the server VAD then waits out its silence window.
TTFA_LABEL = (
    "timing starts at the last user speech chunk sent and includes the server VAD silence "
    "window (F8)"
)


@dataclass(frozen=True)
class TtfaSummary:
    p50_ms: float | None
    p95_ms: float | None
    n: int
    label: str


@dataclass(frozen=True)
class BargeinSummary:
    p50_ms: float | None
    max_ms: float | None
    n: int


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile: the value at 1-based rank ceil(p / 100 * n) of the sorted list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def ttfa_summary(turns: list[TurnRecord]) -> TtfaSummary:
    """AC-27, AC-48: scripted turns only, never live-session turns."""
    values = [t.ttfa_ms for t in turns if t.kind == "scripted" and t.ttfa_ms is not None]
    return TtfaSummary(percentile(values, 50), percentile(values, 95), len(values), TTFA_LABEL)


def bargein_summary(turns: list[TurnRecord]) -> BargeinSummary:
    """AC-29, AC-54: p50 and max over measured interruptions; "not measured" turns are left out."""
    values = [
        t.bargein_ms for t in turns if t.bargein_status == "measured" and t.bargein_ms is not None
    ]
    return BargeinSummary(percentile(values, 50), max(values) if values else None, len(values))
