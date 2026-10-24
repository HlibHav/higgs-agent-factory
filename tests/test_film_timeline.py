"""Timeline math: beats, lead and tail, take window, cap, graphic slots, highlight cues
(AC-34..AC-38). Pure; durations are made up."""

import pytest

from factory.film.line_data import Timeline, load_lines
from factory.film.timeline import (
    CAP_S,
    FPS,
    LEAD_S,
    TAIL_S,
    OverCap,
    TakeWindow,
    build_timeline,
    check_cap,
    graphics_timeline,
    highlight_cues,
    line_start_s,
    report,
)

LINES = load_lines()
IDS = [n.id for b in LINES.beats for n in b.narrator]


def _durs(d: float = 1.0) -> dict[str, float]:
    return dict.fromkeys(IDS, d)


def test_constants() -> None:
    assert (LEAD_S, TAIL_S, FPS, CAP_S) == (0.4, 0.6, 30, 180.0)


def test_end_card_holds_at_least_eight_seconds() -> None:
    # Glib, after the first cut: 3.8 s was too short to read the card's notes.
    t = build_timeline(LINES, _durs(1.0), TakeWindow(2.0, 12.0))
    g = graphics_timeline(t, LINES)
    slot = next(s for s in g.graphics if s.id == "end-card")
    assert slot.frames >= 8 * FPS
    assert g.total_frames == round(t.total_s * FPS)  # the beat grows, the film ends on the card


def test_beat_is_line_plus_lead_and_tail() -> None:
    t = build_timeline(LINES, _durs(1.0), TakeWindow(2.0, 12.0))
    by = {b.number: b for b in t.beats}
    assert by[1].duration_s == pytest.approx(0.4 + 2.0 + 0.6)
    assert by[5].duration_s == pytest.approx(0.4 + 8.0 + 0.6)
    assert by[7].duration_s == pytest.approx(0.4 + 1.0 + 0.6 + 10.0 + 0.4 + 1.0 + 0.6)
    assert by[1].start_s == 0.0
    assert by[2].start_s == pytest.approx(by[1].duration_s)
    assert by[1].narration[0].start_s == pytest.approx(0.4)
    assert by[1].narration[1].start_s == pytest.approx(1.4)  # back to back, no gap


def test_beat_rounds_up_to_whole_frames() -> None:
    t = build_timeline(LINES, _durs(1.013), TakeWindow(0.0, 1.0))
    first = t.beats[0].duration_s
    assert first is not None
    assert first * FPS == pytest.approx(round(first * FPS))
    assert first >= 0.4 + 2 * 1.013 + 0.6
    assert first < 0.4 + 2 * 1.013 + 0.6 + 1 / FPS


def test_no_narrator_over_take() -> None:
    t = build_timeline(LINES, _durs(1.0), TakeWindow(2.0, 12.0))
    b7 = next(b for b in t.beats if b.number == 7)
    assert b7.take is not None
    assert b7.take.end_s - b7.take.start_s == pytest.approx(10.0)
    for line in b7.narration:
        assert line.end_s <= b7.take.start_s or line.start_s >= b7.take.end_s
    intro, outro = b7.narration
    assert (intro.id, outro.id) == ("b7-intro", "b7-outro")
    assert intro.end_s + 0.6 == pytest.approx(b7.take.start_s)
    assert b7.take.end_s + 0.4 == pytest.approx(outro.start_s)


def test_without_take_beat7_and_total_unknown() -> None:
    t = build_timeline(LINES, _durs(1.0), None)
    by = {b.number: b for b in t.beats}
    assert by[7].duration_s is None and t.total_s is None
    assert by[6].duration_s is not None
    assert "beat 7: no take window" in " ".join(report(t, LINES))


def test_report_against_targets_and_180() -> None:
    d = _durs(1.0)
    d["b5-s1"] = 41.6  # beat 5: 0.4 + 7 + 41.6 + 0.6 = 49.6
    t = build_timeline(LINES, d, TakeWindow(0.0, 20.0))
    lines = report(t, LINES)
    assert "beat 5: 49.6 s (target 45 s, +4.6 s)" in lines
    assert lines[0].startswith("beat 1: 3.0 s (target 14 s, ")
    assert lines[-1].startswith("total: ") and " s of 180 s (" in lines[-1]


def _total_tuned(total_s: float) -> dict[str, float]:
    """Durations (multiples of 0.1 s) whose film is exactly `total_s` long."""
    d = _durs(1.0)
    base = build_timeline(LINES, d, TakeWindow(0.0, 10.0)).total_s
    assert base is not None
    d["b5-s1"] += total_s - base  # not an end-card line: the card's hold would absorb it
    return d


def test_185_refused_180_accepted() -> None:
    ok = build_timeline(LINES, _total_tuned(180.0), TakeWindow(0.0, 10.0))
    assert ok.total_s == pytest.approx(180.0)
    check_cap(ok, LINES)  # exactly 5400 frames is allowed
    over = build_timeline(LINES, _total_tuned(185.0), TakeWindow(0.0, 10.0))
    with pytest.raises(OverCap) as info:
        check_cap(over, LINES)
    assert any(line.startswith("total: 185.0 s of 180 s (+5.0 s)") for line in info.value.overruns)
    assert any(line.startswith("beat 5:") for line in info.value.overruns)


def test_graphic_slot_frames() -> None:
    d = _durs(1.0)
    d["b1-s1"], d["b1-s2"] = 4.0, 6.0  # beat 1: 0.4 + 10 + 0.6 = 11.0 s
    t = build_timeline(LINES, d, TakeWindow(0.0, 10.0))
    tl = graphics_timeline(t, LINES)
    assert isinstance(tl, Timeline)
    slots = {s.id: s for s in tl.graphics}
    assert slots["hook"].frames == 330
    assert [(c.id, c.frame) for c in slots["hook"].cues] == [("verdict-stamp", 12 + 120)]
    b8 = next(b for b in t.beats if b.number == 8)
    assert b8.duration_s is not None
    s3 = line_start_s(t, "b8-s3")
    assert slots["end-card"].frames == round((b8.start_s + b8.duration_s - s3) * FPS)
    assert slots["end-card"].cues == []
    assert tl.total_frames == round((t.total_s or 0) * FPS)
    assert [s.id for s in tl.graphics] == ["hook", "market", "decision", "end-card"]


def test_graphics_timeline_needs_a_take() -> None:
    t = build_timeline(LINES, _durs(1.0), None)
    with pytest.raises(ValueError, match="take"):
        graphics_timeline(t, LINES)


def test_highlight_cues_at_sentence_starts() -> None:
    t = build_timeline(LINES, _durs(2.0), TakeWindow(0.0, 10.0))
    cues = {c.id: c for c in highlight_cues(t, LINES)}
    assert set(cues) == {h.id for h in LINES.highlights}
    for h in LINES.highlights:
        assert cues[h.id].start_s == pytest.approx(line_start_s(t, h.at_line))  # within 0.5 s
    b5 = next(b for b in t.beats if b.number == 5)
    assert b5.duration_s is not None
    beat_end = b5.start_s + b5.duration_s  # type: ignore[operator]
    assert cues["v1-verdict"].end_s == pytest.approx(cues["v1-failed-skills"].start_s)
    assert cues["v2-verdict"].end_s == pytest.approx(beat_end)  # same start as run-ids
    assert cues["run-ids"].end_s == pytest.approx(beat_end)
