"""AC-27, AC-48 (TTFA) and AC-29, AC-54 (barge-in aggregate)."""

from factory.gate.metrics import TTFA_LABEL, bargein_summary, percentile, ttfa_summary
from factory.gate.records import TurnRecord


def _turn(ttfa=None, kind="scripted", bargein=None, status=None) -> TurnRecord:
    return TurnRecord("s", 0, kind, ttfa, bargein, status)


def test_percentile_method_nearest_rank():
    """Nearest-rank: the value at 1-based rank ceil(p/100 * n) of the sorted list."""
    values = [float(v) for v in range(10, 210, 10)]  # 20 values, 10..200
    assert percentile(values, 50) == 100.0  # rank 10
    assert percentile(values, 95) == 190.0  # rank 19
    assert percentile(values, 100) == 200.0
    assert percentile([5.0], 95) == 5.0


def test_ac27_p50_p95_n_and_label():
    turns = [_turn(ttfa=float(v)) for v in reversed(range(10, 210, 10))]
    s = ttfa_summary(turns)
    assert (s.p50_ms, s.p95_ms, s.n) == (100.0, 190.0, 20)
    assert s.label == TTFA_LABEL
    assert "last user speech chunk" in TTFA_LABEL and "VAD" in TTFA_LABEL


def test_ac27_no_values_gives_none():
    s = ttfa_summary([_turn(ttfa=None)])
    assert (s.p50_ms, s.p95_ms, s.n) == (None, None, 0)


def test_ac48_scripted_only():
    turns = [_turn(ttfa=float(v)) for v in range(1, 11)]
    turns += [_turn(ttfa=9999.0, kind="live") for _ in range(5)]
    s = ttfa_summary(turns)
    assert s.n == 10
    assert s.p95_ms == 10.0


def test_ac29_ac54_not_measured_excluded():
    turns = [
        _turn(bargein=200.0, status="measured"),
        _turn(bargein=300.0, status="measured"),
        _turn(bargein=900.0, status="measured"),
        _turn(bargein=None, status="not measured"),
        _turn(),  # not an interrupt turn
    ]
    b = bargein_summary(turns)
    assert (b.p50_ms, b.max_ms, b.n) == (300.0, 900.0, 3)


def test_ac29_nothing_measured():
    b = bargein_summary([_turn(bargein=None, status="not measured")])
    assert (b.p50_ms, b.max_ms, b.n) == (None, None, 0)


def test_ac29_status_not_measured_ignores_a_stray_value():
    b = bargein_summary([_turn(bargein=50.0, status="not measured")])
    assert b.n == 0
