"""Film timeline math (AC-34..AC-38): beat lengths, narrator and take placement, the 180 s cap,
graphic slots and highlight cues. Pure; durations come from the stem manifest.

All times are seconds on the film's clock. Beat lengths are rounded up to whole frames.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from factory.film.line_data import CaptionCue, Cue, GraphicSlot, LineData, Timeline

LEAD_S = 0.4  # AC-34
TAIL_S = 0.6  # AC-34
FPS = 30  # AC-58
CAP_S = 180.0  # AC-37, a hard cap
CAP_FRAMES = int(CAP_S * FPS)
TAKE_PRE_S = 0.5  # take window opens this long before T1 starts
TAKE_POST_S = 0.8  # and closes this long after the reply to T2 ends
TAKE_BEAT = 7
_EPS = 1e-6


@dataclass(frozen=True)
class TakeWindow:
    """The kept stretch of the take, in take-audio time."""

    start_s: float
    end_s: float


@dataclass(frozen=True)
class Placed:
    id: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class BeatSlot:
    number: int
    start_s: float | None
    duration_s: float | None
    narration: list[Placed] = field(default_factory=list)
    take: Placed | None = None


@dataclass(frozen=True)
class FilmTimeline:
    beats: list[BeatSlot]

    @property
    def total_s(self) -> float | None:
        if any(b.duration_s is None for b in self.beats):
            return None
        return sum(b.duration_s for b in self.beats if b.duration_s is not None)

    def beat(self, number: int) -> BeatSlot:
        return next(b for b in self.beats if b.number == number)


class OverCap(Exception):
    def __init__(self, overruns: list[str]) -> None:
        super().__init__("; ".join(overruns))
        self.overruns = overruns


def _round_up_to_frame(seconds: float) -> float:
    return math.ceil(seconds * FPS - _EPS) / FPS


def build_timeline(
    lines: LineData, durations: Mapping[str, float], take: TakeWindow | None
) -> FilmTimeline:
    """Each beat is its narrator line plus a 0.4 s lead and a 0.6 s tail; beat 7 is the intro,
    the take window, then the outro, each with lead and tail. A missing take leaves beat 7 and
    the placement of every later beat unknown (None)."""
    slots: list[BeatSlot] = []
    cursor: float | None = 0.0
    for beat in lines.beats:
        lengths = [durations[n.id] for n in beat.narrator]
        if beat.number == TAKE_BEAT:
            if take is None:
                slots.append(BeatSlot(beat.number, cursor, None))
                cursor = None
                continue
            window = take.end_s - take.start_s
            raw = LEAD_S + lengths[0] + TAIL_S + window + LEAD_S + lengths[1] + TAIL_S
        else:
            raw = LEAD_S + sum(lengths) + TAIL_S
        duration = _round_up_to_frame(raw)
        narration: list[Placed] = []
        placed_take: Placed | None = None
        if cursor is not None:
            at = cursor + LEAD_S
            for i, n in enumerate(beat.narrator):
                narration.append(Placed(n.id, at, at + lengths[i]))
                at += lengths[i]
                if beat.number == TAKE_BEAT and i == 0 and take is not None:
                    at += TAIL_S
                    placed_take = Placed("take", at, at + (take.end_s - take.start_s))
                    at = placed_take.end_s + LEAD_S
        slots.append(BeatSlot(beat.number, cursor, duration, narration, placed_take))
        cursor = None if cursor is None else cursor + duration
    return FilmTimeline(slots)


def _frames(seconds: float) -> int:
    return round(seconds * FPS)


def _delta(value: float) -> str:
    return f"{round(value, 1):+g}"


def report(t: FilmTimeline, lines: LineData) -> list[str]:
    """AC-36: each beat against the screenplay's target, then the total against 180 s."""
    out: list[str] = []
    for beat in lines.beats:
        slot = t.beat(beat.number)
        if slot.duration_s is None:
            out.append(f"beat {beat.number}: no take window yet (target {beat.target_s:g} s)")
            continue
        out.append(
            f"beat {beat.number}: {slot.duration_s:.1f} s (target {beat.target_s:g} s, "
            f"{_delta(slot.duration_s - beat.target_s)} s)"
        )
    total = t.total_s
    if total is None:
        out.append(f"total: unknown without a take window (cap {CAP_S:g} s)")
    else:
        out.append(f"total: {total:.1f} s of {CAP_S:g} s ({total - CAP_S:+.1f} s)")
    return out


def check_cap(t: FilmTimeline, lines: LineData) -> None:
    """AC-37: refuse above 5400 frames and name the overrun per beat."""
    total = t.total_s
    if total is None:
        raise ValueError("the timeline has no take window, so its length is unknown")
    if _frames(total) <= CAP_FRAMES:
        return
    overruns = [
        line
        for beat, line in zip(lines.beats, report(t, lines), strict=False)
        if (t.beat(beat.number).duration_s or 0.0) > beat.target_s
    ]
    overruns.append(report(t, lines)[-1])
    raise OverCap(overruns)


def line_start_s(t: FilmTimeline, line_id: str) -> float:
    for slot in t.beats:
        for placed in slot.narration:
            if placed.id == line_id:
                return placed.start_s
    raise KeyError(f"no narrator line {line_id!r} on the timeline")


def _beat_of_line(lines: LineData, line_id: str) -> int:
    return next(b.number for b in lines.beats for n in b.narrator if n.id == line_id)


def graphics_timeline(
    t: FilmTimeline, lines: LineData, captions: list[CaptionCue] | None = None
) -> Timeline:
    """The `Timeline` contract Remotion reads: graphic slots with cue frames relative to each
    slot's start, the film's length and the captions."""
    total = t.total_s
    if total is None:
        raise ValueError("the timeline has no take window: no graphics timeline without a take")
    slots: list[GraphicSlot] = []
    for g in lines.graphics:
        slot = t.beat(g.beat)
        assert slot.start_s is not None and slot.duration_s is not None
        start = slot.start_s if g.starts_at_line is None else line_start_s(t, g.starts_at_line)
        start_f = _frames(start)
        end_f = _frames(slot.start_s + slot.duration_s)
        cues = [Cue(id=c.id, frame=_frames(line_start_s(t, c.at_line)) - start_f) for c in g.cues]
        slots.append(GraphicSlot(id=g.id, frames=end_f - start_f, cues=cues))
    return Timeline(
        schema_version=1,
        fps=30,
        width=1920,
        height=1080,
        total_frames=_frames(total),
        graphics=slots,
        captions=captions or [],
    )


def highlight_cues(t: FilmTimeline, lines: LineData) -> list[Placed]:
    """AC-38: each beat 5 highlight appears when its sentence starts and lasts until the next,
    later highlight or the beat's end."""
    starts = {h.id: line_start_s(t, h.at_line) for h in lines.highlights}
    out: list[Placed] = []
    for h in lines.highlights:
        slot = t.beat(_beat_of_line(lines, h.at_line))
        assert slot.start_s is not None and slot.duration_s is not None
        later = [s for s in starts.values() if s > starts[h.id] + _EPS]
        end = min(later) if later else slot.start_s + slot.duration_s
        out.append(Placed(h.id, starts[h.id], end))
    return out
