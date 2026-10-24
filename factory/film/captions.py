"""Caption cues for the film (AC-40, AC-41, AC-55, AC-61).

This ffmpeg build has neither `subtitles` nor `drawtext`, so captions are data: `CaptionCue`s go
into `timeline.json` and Remotion draws a transparent overlay that the render lays over the
film. Text is carried verbatim as a JSON string and drawn as plain text by the overlay, so
override syntax such as `{\\b1}` or `<b>` in an agent transcript has no effect.
"""

from collections.abc import Sequence

from factory.film.line_data import CaptionCue, LineData
from factory.film.page_port import CallerPlayed, PageEvent
from factory.film.takes import TakeVerdict, effective_end, t1_reply_chunks, t2_reply_chunks
from factory.film.timeline import FPS, FilmTimeline, end_card_lines


def _frame(seconds: float) -> int:
    return max(0, round(seconds * FPS))


def _cue(cue_id: str, kind: str, text: str, start_s: float, end_s: float) -> CaptionCue:
    start = _frame(start_s)
    end = max(_frame(end_s), start + 1)
    return CaptionCue(id=cue_id, kind=kind, text=text, start_frame=start, end_frame=end)  # type: ignore[arg-type]


def narrator_captions(t: FilmTimeline, lines: LineData) -> list[CaptionCue]:
    """AC-61: each narrator sentence, for the span of its stem. Beat 7's sentences appear only
    once the take window is known. Lines spoken over the end card stay uncaptioned (AC-45), so
    the caption never covers the card's notes."""
    texts = {n.id: n.text for b in lines.beats for n in b.narrator}
    on_card = end_card_lines(lines)
    return [
        _cue(p.id, "narrator", texts[p.id], p.start_s, p.end_s)
        for slot in t.beats
        for p in slot.narration
        if p.id not in on_card
    ]


def take_captions(
    events: Sequence[PageEvent],
    t1: CallerPlayed,
    t2: CallerPlayed | None,
    verdict: TakeVerdict,
    lines: LineData,
    offset_s: float,
) -> list[CaptionCue]:
    """Caller lines (AC-40), the interrupted reply to T1 (AC-55) and the reply to T2 (AC-41).
    Film seconds = page seconds + `offset_s`."""
    dialogue = {d.id: d.text for d in lines.dialogue}
    cues = [_cue("T1", "caller", dialogue["T1"], t1.t + offset_s, t1.t + t1.duration_s + offset_s)]
    if t2 is not None:
        cues.append(
            _cue("T2", "caller", dialogue["T2"], t2.t + offset_s, t2.t + t2.duration_s + offset_s)
        )
        reply = t1_reply_chunks(events, t1, t2)
        ends = [end for c in reply if (end := effective_end(c, events)) is not None]
        if reply and ends:
            # The reply is shown as the fixed marker, never as text: the agent's words for a
            # cancelled response were not spoken (F27).
            start = min(c.start for c in reply)
            cues.append(
                _cue(
                    "T1-reply",
                    "interrupted",
                    lines.interrupted_caption,
                    start + offset_s,
                    max(ends) + offset_s,
                )
            )
        chunks = t2_reply_chunks(events, t2)
        if verdict.t2_transcript is not None and chunks:
            cues.append(
                _cue(
                    "T2-reply",
                    "reply",
                    verdict.t2_transcript,
                    min(c.start for c in chunks) + offset_s,
                    max(c.end for c in chunks) + offset_s,
                )
            )
    return cues
