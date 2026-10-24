"""The take rule over page events (AC-18..AC-27). Pure: events are made up; the page clock is
in seconds."""

import pytest

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
from factory.film.takes import (
    NO_REPLY_S,
    STOP_TOL_S,
    effective_end,
    judge_take,
    reply_playing_at,
    t1_at,
    t1_reply_chunks,
    t2_at,
)

T1 = CallerPlayed(1.0, "T1", 3.0)  # T1 plays 1.0-4.0


def _t2(at: float) -> CallerPlayed:
    return CallerPlayed(at, "T2", 2.0)


def _good(signal: float = 6.7, stop_at: float = 6.72) -> list[PageEvent]:
    """T1 reply 5.0-9.0 in two chunks, T2 at 6.5, signal 6.7, stop at `stop_at`, T2 reply."""
    return [
        Ready(0.5, True),
        T1,
        TtfaShown(5.0, 800.0, "speech_stopped to first audio delta"),
        AssistantChunk(5.0, 5.0, 7.0),
        AssistantChunk(5.1, 7.0, 9.0),
        _t2(6.5),
        SpeechStartedSignal(signal),
        PlaybackStopped(stop_at),
        TtfaShown(9.5, 700.0, "speech_stopped to first audio delta"),
        AssistantChunk(9.5, 9.5, 11.0),
        TranscriptShown(11.2, "I can't share that. Let's go back to the policy."),
    ]


def test_t1_after_ready_and_first() -> None:
    assert t1_at(Ready(3.0, True)) == pytest.approx(3.5)


def test_t2_due_first_audio_plus_1_5_any_length() -> None:
    short = [T1, AssistantChunk(5.0, 5.0, 5.8)]
    long_ = [T1, AssistantChunk(5.0, 5.0, 11.0)]
    assert t2_at(short, T1) == pytest.approx(6.5)
    assert t2_at(long_, T1) == pytest.approx(6.5)
    assert t2_at([T1, AssistantChunk(0.5, 0.5, 0.9)], T1) is None  # before T1 started
    assert t2_at([T1], T1) is None


def test_reply_ended_before_t2_dropped() -> None:
    events: list[PageEvent] = [Ready(0.5, True), T1, AssistantChunk(5.0, 5.0, 5.9)]
    assert not reply_playing_at(events, T1, 6.5)
    verdict = judge_take(events, T1, None)
    assert verdict.status == "dropped"
    assert verdict.reasons == ["T1 reply ended before T2"]
    assert reply_playing_at([*events, AssistantChunk(5.1, 5.9, 8.0)], T1, 6.5)


def test_no_reply_within_10s_dropped() -> None:
    events: list[PageEvent] = [Ready(0.5, True), T1]
    verdict = judge_take(events, T1, None)
    assert verdict.reasons == ["no reply to T1"]
    late: list[PageEvent] = [*events, AssistantChunk(14.5, 14.5, 16.0)]  # T1 ends 4.0; 10 s => 14.0
    assert NO_REPLY_S == 10.0
    assert judge_take(late, T1, None).reasons == ["no reply to T1"]
    ok_edge = [*events, AssistantChunk(13.9, 13.9, 14.4)]
    assert "no reply to T1" not in judge_take(ok_edge, T1, None).reasons


def test_effective_end_clipped_by_stop() -> None:
    chunk = AssistantChunk(5.0, 5.0, 6.4)
    assert effective_end(chunk, [PlaybackStopped(6.05)]) == pytest.approx(6.05)
    assert effective_end(chunk, []) == 6.4
    assert effective_end(chunk, [PlaybackStopped(7.0)]) == 6.4  # stop after the chunk ended


def test_chunk_stopped_before_start_never_played() -> None:
    chunk = AssistantChunk(5.0, 6.0, 7.0)
    assert effective_end(chunk, [PlaybackStopped(5.5)]) is None
    assert effective_end(chunk, [PlaybackStopped(4.0)]) == 7.0  # a stop before it arrived
    assert STOP_TOL_S == 0.05


def test_audio_stopped_on_t2_three_timelines() -> None:
    # (a) the page stops within tolerance of the signal: true
    a = judge_take(_good(), T1, _t2(6.5))
    assert a.status == "candidate" and a.reasons == []
    # (b) no stop at all: audio plays on after the signal
    b = [e for e in _good() if not isinstance(e, PlaybackStopped)]
    vb = judge_take(b, T1, _t2(6.5))
    assert vb.status == "dropped" and vb.reasons == ["audio did not stop on T2"]
    # (c) the signal came after the reply had finished playing
    c: list[PageEvent] = [
        Ready(0.5, True),
        T1,
        AssistantChunk(5.0, 5.0, 6.0),
        _t2(6.5),
        SpeechStartedSignal(6.7),
        PlaybackStopped(6.72),
        TranscriptShown(9.0, "x"),
    ]
    vc = judge_take(c, T1, _t2(6.5))
    assert vc.reasons == ["audio did not stop on T2"]
    # (d) a chunk received after the signal plays out after it
    d = [*_good(), AssistantChunk(6.9, 6.9, 7.5)]
    d.sort(key=lambda e: getattr(e, "t", getattr(e, "t_received", 0.0)))
    assert judge_take(d, T1, _t2(6.5)).reasons == ["audio did not stop on T2"]
    # (e) no signal at all
    e = [x for x in _good() if not isinstance(x, SpeechStartedSignal)]
    assert judge_take(e, T1, _t2(6.5)).reasons == ["audio did not stop on T2"]


def test_t1_reply_chunks_window() -> None:
    events = _good()
    t2 = _t2(6.5)
    chunks = t1_reply_chunks(events, T1, t2)
    assert [c.t_received for c in chunks] == [5.0, 5.1]


def test_stop_latency_350ms() -> None:
    v = judge_take(_good(signal=6.82, stop_at=6.85), T1, _t2(6.5))
    assert v.stop_latency_ms == pytest.approx(350.0)
    assert v.t2_offset_s == pytest.approx(1.5)


def test_t2_split_flag_n2() -> None:
    events = _good()
    events.insert(-2, TtfaShown(10.2, 650.0, "speech_stopped to first audio delta"))
    events.sort(key=lambda e: getattr(e, "t", getattr(e, "t_received", 0.0)))
    v = judge_take(events, T1, _t2(6.5))
    assert v.split_n == 2
    assert judge_take(_good(), T1, _t2(6.5)).split_n is None


def test_candidate_rule_with_reasons() -> None:
    events = [e for e in _good() if not isinstance(e, PlaybackStopped)]
    events.insert(1, BannerShown(0.6))
    v = judge_take(events, T1, _t2(6.5))
    assert v.status == "dropped"
    assert v.reasons == ["not released", "audio did not stop on T2"]
    assert v.stop_run == "not released"
    assert judge_take([Ready(0.5, False), T1], T1, None).reasons[0] == "not released"


def test_session_end_before_t2_reply_dropped_with_reason() -> None:
    events = [e for e in _good() if not isinstance(e, TranscriptShown)]
    events.append(SessionEndedShown(10.0, "inactivity", "The session ended for inactivity."))
    v = judge_take(events, T1, _t2(6.5))
    assert v.status == "dropped" and "inactivity" in v.reasons
    assert v.end_reason == "inactivity" and v.stop_run is None
    quota = [e for e in events if not isinstance(e, SessionEndedShown)]
    quota.append(SessionEndedShown(7.0, "quota refused", "refused"))
    assert judge_take(quota, T1, _t2(6.5)).stop_run == "quota refused"
    # an end after the T2 reply completed is not a drop
    late = [*_good(), SessionEndedShown(12.0, "closed", "The session was closed.")]
    assert judge_take(late, T1, _t2(6.5)).status == "candidate"


def test_t2_transcript_and_ttfa_recorded() -> None:
    v = judge_take(_good(), T1, _t2(6.5))
    assert v.t2_transcript == "I can't share that. Let's go back to the policy."
    assert v.ttfa == [
        (800.0, "speech_stopped to first audio delta"),
        (700.0, "speech_stopped to first audio delta"),
    ]
    blank = [TranscriptShown(11.2, "  ") if isinstance(e, TranscriptShown) else e for e in _good()]
    assert judge_take(blank, T1, _t2(6.5)).t2_transcript is None
