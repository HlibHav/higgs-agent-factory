"""Captions as cues for the overlay (AC-40, AC-41, AC-55, AC-61). ffmpeg has no `subtitles` or
`drawtext` here, so lane B draws the cues; these tests pin the text and the spans."""

import pytest

from factory.film.captions import narrator_captions, take_captions
from factory.film.line_data import Timeline, load_lines
from factory.film.page_port import (
    AssistantChunk,
    CallerPlayed,
    PageEvent,
    PlaybackStopped,
    Ready,
    SpeechStartedSignal,
    TranscriptShown,
    TtfaShown,
)
from factory.film.takes import judge_take
from factory.film.timeline import FPS, TakeWindow, build_timeline, graphics_timeline

LINES = load_lines()
DURS = {n.id: 1.0 for b in LINES.beats for n in b.narrator}
T1 = CallerPlayed(1.0, "T1", 3.0)
T2 = CallerPlayed(6.5, "T2", 2.0)
REPLY = "{\\b1}Not that.{\\i0} \\N <b>bold</b> \\y\nsecond line"


def _events(reply: str = REPLY) -> list[PageEvent]:
    return [
        Ready(0.5, True),
        T1,
        TtfaShown(5.0, 800.0, "label"),
        AssistantChunk(5.0, 5.0, 9.0),
        T2,
        SpeechStartedSignal(6.7),
        PlaybackStopped(6.72),
        TtfaShown(9.5, 700.0, "label"),
        AssistantChunk(9.5, 9.5, 11.0),
        TranscriptShown(11.2, reply),
    ]


def _frames(s: float) -> int:
    return round(s * FPS)


def test_narrator_caption_beat1() -> None:
    t = build_timeline(LINES, DURS, TakeWindow(0.0, 10.0))
    cues = narrator_captions(t, LINES)
    beat1 = [c for c in cues if c.id.startswith("b1-")]
    assert [c.text for c in beat1] == [n.text for n in LINES.beats[0].narrator]
    assert all(c.kind == "narrator" for c in cues)
    placed = t.beats[0].narration
    assert [(c.start_frame, c.end_frame) for c in beat1] == [
        (_frames(p.start_s), _frames(p.end_s)) for p in placed
    ]
    end_card = next(g for g in LINES.graphics if g.id == "end-card")
    assert end_card.starts_at_line is not None
    assert len(cues) == sum(len(b.narrator) for b in LINES.beats) - 1
    assert {"b7-intro", "b7-outro"} <= {c.id for c in cues}


def test_no_caption_while_the_end_card_shows() -> None:
    t = build_timeline(LINES, DURS, TakeWindow(0.0, 10.0))
    g = graphics_timeline(t, LINES, narrator_captions(t, LINES))
    slot = next(s for s in g.graphics if s.id == "end-card")
    card_start = g.total_frames - slot.frames
    assert all(c.end_frame <= card_start for c in narrator_captions(t, LINES))


def test_t1_caption_exact_text_and_span() -> None:
    verdict = judge_take(_events(), T1, T2)
    cues = take_captions(_events(), T1, T2, verdict, LINES, offset_s=100.0)
    t1 = next(c for c in cues if c.id == "T1")
    assert t1.kind == "caller" and t1.text == LINES.dialogue[0].text
    assert (t1.start_frame, t1.end_frame) == (_frames(101.0), _frames(104.0))
    t2 = next(c for c in cues if c.id == "T2")
    assert t2.text == LINES.dialogue[1].text
    assert (t2.start_frame, t2.end_frame) == (_frames(106.5), _frames(108.5))


def test_t1_reply_captioned_interrupted_only() -> None:
    events = _events()
    events.insert(4, TranscriptShown(5.5, "What the agent had planned to say about refunds"))
    verdict = judge_take(events, T1, T2)
    cues = take_captions(events, T1, T2, verdict, LINES, offset_s=0.0)
    interrupted = [c for c in cues if c.kind == "interrupted"]
    assert len(interrupted) == 1
    cue = interrupted[0]
    assert cue.text == LINES.interrupted_caption == "(interrupted)"
    assert (cue.start_frame, cue.end_frame) == (_frames(5.0), _frames(6.72))  # until the stop
    assert all("planned to say" not in c.text for c in cues)  # F27: never unspoken text


def test_t2_reply_caption_literal_markup() -> None:
    verdict = judge_take(_events(), T1, T2)
    cues = take_captions(_events(), T1, T2, verdict, LINES, offset_s=0.0)
    reply = next(c for c in cues if c.kind == "reply")
    assert reply.text == REPLY  # plain text, no escaping, nothing interpreted
    assert (reply.start_frame, reply.end_frame) == (_frames(9.5), _frames(11.0))
    t = build_timeline(LINES, DURS, TakeWindow(0.0, 10.0))
    timeline = graphics_timeline(t, LINES, [*narrator_captions(t, LINES), *cues])
    again = Timeline.model_validate_json(timeline.model_dump_json())
    assert next(c for c in again.captions if c.kind == "reply").text == REPLY


def test_no_reply_caption_without_a_transcript() -> None:
    events = [e for e in _events() if not isinstance(e, TranscriptShown)]
    verdict = judge_take(events, T1, T2)
    cues = take_captions(events, T1, T2, verdict, LINES, offset_s=0.0)
    assert not [c for c in cues if c.kind == "reply"]


def test_dropped_take_without_t2_has_only_t1_and_interrupted_absent() -> None:
    events: list[PageEvent] = [Ready(0.5, True), T1, AssistantChunk(5.0, 5.0, 5.9)]
    verdict = judge_take(events, T1, None)
    cues = take_captions(events, T1, None, verdict, LINES, offset_s=0.0)
    assert [c.id for c in cues if c.kind == "caller"] == ["T1"]
    assert [c.kind for c in cues if c.kind == "interrupted"] == []  # nothing interrupted it


@pytest.mark.parametrize("offset", [0.0, 12.5])
def test_cues_never_negative(offset: float) -> None:
    verdict = judge_take(_events(), T1, T2)
    for c in take_captions(_events(), T1, T2, verdict, LINES, offset_s=offset):
        assert 0 <= c.start_frame < c.end_frame
