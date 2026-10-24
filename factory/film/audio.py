"""Audio analysis for stems: duration and internal silences (AC-15). Domain: stdlib only."""

import array
import math
import sys

RATE = 24000  # F4, F22: 24 kHz s16le mono
VAD_SILENCE_S = 0.5  # F8: the server VAD silence window (silence_duration_ms 500)
SILENCE_DBFS = -45.0
WINDOW_S = 0.02
_WINDOW = int(RATE * WINDOW_S)
_SILENT_WINDOWS_REFUSED = round(VAD_SILENCE_S / WINDOW_S)


class StemRejected(Exception):
    """A stem cannot be used in a take. `gap_start_s` and `gap_s` locate the silence."""

    def __init__(self, message: str, line_id: str, gap_start_s: float, gap_s: float) -> None:
        super().__init__(message)
        self.line_id = line_id
        self.gap_start_s = gap_start_s
        self.gap_s = gap_s


def pcm_duration_s(pcm: bytes) -> float:
    return (len(pcm) // 2) / RATE


def _samples(pcm: bytes) -> array.array[int]:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _silent_flags(pcm: bytes) -> list[bool]:
    """One flag per whole 20 ms window: True when its RMS is below `SILENCE_DBFS`."""
    samples = _samples(pcm)
    flags: list[bool] = []
    for start in range(0, len(samples) - _WINDOW + 1, _WINDOW):
        window = samples[start : start + _WINDOW]
        mean_sq = sum(s * s for s in window) / _WINDOW
        db = 10 * math.log10(mean_sq / 32768**2) if mean_sq > 0 else -200.0
        flags.append(db < SILENCE_DBFS)
    return flags


def internal_silences(pcm: bytes) -> list[tuple[float, float]]:
    """(start_s, length_s) of every silent run between the first and last non-silent window.
    Leading and trailing silence is not internal. All-silent input has none."""
    flags = _silent_flags(pcm)
    loud = [i for i, silent in enumerate(flags) if not silent]
    if not loud:
        return []
    out: list[tuple[float, float]] = []
    run_start: int | None = None
    for i in range(loud[0], loud[-1] + 1):
        if flags[i] and run_start is None:
            run_start = i
        elif not flags[i] and run_start is not None:
            out.append((run_start * WINDOW_S, (i - run_start) * WINDOW_S))
            run_start = None
    return out


def check_t2(pcm: bytes, line_id: str = "T2") -> None:
    """AC-15: refuse a stem with a silence at or above the VAD window, or one that is all
    silence (nothing to say)."""
    flags = _silent_flags(pcm)
    if flags and all(flags) or not flags:
        raise StemRejected(
            f"{line_id} is silent: no audio above {SILENCE_DBFS:.0f} dBFS",
            line_id,
            0.0,
            pcm_duration_s(pcm),
        )
    for start_s, length_s in internal_silences(pcm):
        if round(length_s / WINDOW_S) >= _SILENT_WINDOWS_REFUSED:
            raise StemRejected(
                f"{line_id} has a {length_s:.2f} s silence at {start_s:.2f} s",
                line_id,
                start_s,
                length_s,
            )
