"""The take rule over page events (AC-18..AC-27). Pure: events in, a verdict out.

The interruption is judged only from the page's own signals and its played audio, never from
the transcript (F27: the transcript arrives whole). All times are page-clock seconds.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from factory.film.page_port import (
    AssistantChunk,
    BannerShown,
    CallerPlayed,
    PageEvent,
    PlaybackStopped,
    Ready,
    SessionEndedShown,
    SpeechStartedSignal,
    TranscriptShown,
    TtfaShown,
)

T1_AFTER_READY_S = 0.5  # AC-18 (assumed default: the plan's open question)
T2_AFTER_FIRST_AUDIO_S = 1.5  # AC-19
NO_REPLY_S = 10.0  # AC-21
STOP_TOL_S = 0.05  # AC-22: audio may end this long after the signal (plan's assumed default)

REASON_REPLY_ENDED = "T1 reply ended before T2"  # AC-20
REASON_NO_REPLY = "no reply to T1"  # AC-21
REASON_NO_STOP = "audio did not stop on T2"  # AC-22
REASON_NOT_RELEASED = "not released"  # AC-29
REASON_NO_T2_REPLY = "no reply to T2"
QUOTA_REFUSED = "quota refused"  # F13


@dataclass(frozen=True)
class TakeVerdict:
    status: Literal["candidate", "dropped"]
    reasons: list[str] = field(default_factory=list)
    split_n: int | None = None
    t2_offset_s: float | None = None
    stop_latency_ms: float | None = None
    t2_transcript: str | None = None
    ttfa: list[tuple[float, str]] = field(default_factory=list)
    end_reason: str | None = None
    stop_run: str | None = None  # "quota refused" or "not released": no further take


def t1_at(ready: Ready) -> float:
    return ready.t + T1_AFTER_READY_S


def _first_reply_chunk(events: Sequence[PageEvent], t1: CallerPlayed) -> AssistantChunk | None:
    chunks = [e for e in events if isinstance(e, AssistantChunk) and e.t_received > t1.t]
    return min(chunks, key=lambda c: c.t_received, default=None)


def t2_at(events: Sequence[PageEvent], t1: CallerPlayed) -> float | None:
    """AC-19: 1.5 s after the first audio of the reply to T1 reached the page, whatever the
    reply's length."""
    first = _first_reply_chunk(events, t1)
    return None if first is None else first.t_received + T2_AFTER_FIRST_AUDIO_S


def t1_reply_chunks(
    events: Sequence[PageEvent], t1: CallerPlayed, t2: CallerPlayed | None
) -> list[AssistantChunk]:
    """Chunks received after the first `ttfa` that follows T1 and before the first `ttfa` that
    follows T2's start (the page carries no response ids)."""
    ttfas = sorted(e.t for e in events if isinstance(e, TtfaShown))
    lo = next((t for t in ttfas if t > t1.t), t1.t)
    hi = float("inf")
    if t2 is not None:
        hi = next((t for t in ttfas if t > t2.t), float("inf"))
    return [
        e
        for e in events
        if isinstance(e, AssistantChunk) and e.t_received > t1.t and lo <= e.t_received < hi
    ]


def t2_reply_chunks(events: Sequence[PageEvent], t2: CallerPlayed) -> list[AssistantChunk]:
    """Chunks received from the first `ttfa` that follows T2's start: the reply to T2."""
    ttfas = sorted(e.t for e in events if isinstance(e, TtfaShown))
    lo = next((x for x in ttfas if x > t2.t), None)
    if lo is None:
        return []
    return [e for e in events if isinstance(e, AssistantChunk) and e.t_received >= lo]


def reply_playing_at(events: Sequence[PageEvent], t1: CallerPlayed, at: float) -> bool:
    """True when a chunk of the reply to T1 is scheduled to be playing at page time `at`."""
    return any(
        e.start <= at < e.end
        for e in events
        if isinstance(e, AssistantChunk) and e.t_received > t1.t
    )


def effective_end(chunk: AssistantChunk, events: Sequence[PageEvent]) -> float | None:
    """When the chunk's audio really ended: its scheduled end, or the first stop that came
    after it was received. None when it was stopped before it began (never played)."""
    stops = [e.t for e in events if isinstance(e, PlaybackStopped) and e.t >= chunk.t_received]
    if not stops:
        return chunk.end
    stop = min(stops)
    if stop <= chunk.start:
        return None
    return min(stop, chunk.end)


def _stopped_on_t2(events: Sequence[PageEvent], t1: CallerPlayed, t2: CallerPlayed) -> bool:
    """AC-22: a speech_started signal came while the reply to T1 was still playing, and none
    of that reply's audio played after it (beyond the tolerance)."""
    signals = sorted(e.t for e in events if isinstance(e, SpeechStartedSignal) and e.t >= t2.t)
    if not signals:
        return False
    s = signals[0]
    reply = t1_reply_chunks(events, t1, t2)
    if not any(c.t_received <= s and c.end > s for c in reply):
        return False
    for chunk in reply:
        end = effective_end(chunk, events)
        if end is not None and end > s + STOP_TOL_S:
            return False
    return True


def judge_take(
    events: Sequence[PageEvent], t1: CallerPlayed | None, t2: CallerPlayed | None
) -> TakeVerdict:
    """AC-26: a candidate only when AC-22 holds and no earlier drop reason applies; otherwise
    dropped with every failed condition named."""
    reasons: list[str] = []
    stop_run: str | None = None
    ready = next((e for e in events if isinstance(e, Ready)), None)
    if any(isinstance(e, BannerShown) for e in events) or (
        ready is not None and ready.released is False
    ):
        reasons.append(REASON_NOT_RELEASED)
        stop_run = REASON_NOT_RELEASED
    ended = next((e for e in events if isinstance(e, SessionEndedShown)), None)
    end_reason = None if ended is None else ended.reason

    t2_reply: TranscriptShown | None = None
    if t2 is not None:
        t2_reply = next((e for e in events if isinstance(e, TranscriptShown) and e.t > t2.t), None)

    first = None if t1 is None else _first_reply_chunk(events, t1)
    if t1 is not None:
        deadline = t1.t + t1.duration_s + NO_REPLY_S
        if first is None or first.t_received > deadline:
            if ended is None or ended.t > deadline:
                reasons.append(REASON_NO_REPLY)
        elif t2 is None and ended is None and stop_run is None:
            reasons.append(REASON_REPLY_ENDED)

    if ended is not None and (t2_reply is None or ended.t < t2_reply.t):
        reasons.append(ended.reason)  # AC-27
        if ended.reason == QUOTA_REFUSED:
            stop_run = stop_run or QUOTA_REFUSED
    elif t2 is not None and t2_reply is None:
        reasons.append(REASON_NO_T2_REPLY)
    if t1 is None and not reasons:
        reasons.append(REASON_NO_REPLY)

    split_n: int | None = None
    offset: float | None = None
    latency_ms: float | None = None
    if t1 is not None and t2 is not None:
        if not _stopped_on_t2(events, t1, t2):
            reasons.append(REASON_NO_STOP)
        count = sum(1 for e in events if isinstance(e, TtfaShown) and e.t > t2.t)
        split_n = count if count > 1 else None
        if first is not None:
            offset = t2.t - first.t_received
        ends = [
            end
            for c in t1_reply_chunks(events, t1, t2)
            if (end := effective_end(c, events)) is not None
        ]
        if ends:
            latency_ms = max(0.0, (max(ends) - t2.t) * 1000.0)

    transcript: str | None = None
    if t2_reply is not None and t2_reply.text.strip():
        transcript = t2_reply.text
    return TakeVerdict(
        status="dropped" if reasons else "candidate",
        reasons=reasons,
        split_n=split_n,
        t2_offset_s=offset,
        stop_latency_ms=latency_ms,
        t2_transcript=transcript,
        ttfa=[(e.ms, e.label) for e in events if isinstance(e, TtfaShown)],
        end_reason=end_reason,
        stop_run=stop_run,
    )
