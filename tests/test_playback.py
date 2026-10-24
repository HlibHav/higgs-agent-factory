"""Paced playback and TTFA (step 14), barge-in timing (step 17c)."""

import asyncio
from pathlib import Path

import pytest

from factory.gate import runner
from factory.gate.playback import CHUNK_MS, play_turn, stream_silence_until, ttfa_ms
from factory.gate.runner import preflight, run_gate
from factory.gate.tts_cache import TurnAudioSource
from factory.ports import AudioDelta, ResponseDone, TranscriptDelta
from tests.doubles import Delay, FakeJudge, FakeSession, FakeSessionFactory, make_spec

BYTES_PER_S = 48_000  # 24 kHz s16le mono (F4)


class FakeClock:
    """Deterministic time: `sleep` advances `now`; nothing really waits."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _speech(seconds: float) -> bytes:
    return b"\x05\x00" * int(seconds * BYTES_PER_S / 2)


def test_chunks_stay_under_f4_limit() -> None:
    clock = FakeClock()
    session = FakeSession(clock=clock)
    asyncio.run(play_turn(session, _speech(1.05), sleep=clock.sleep))
    sizes = [len(s.pcm or b"") for s in session.sends]
    assert CHUNK_MS == 100
    assert max(sizes) <= 4800  # 100 ms of 24 kHz s16le (F4: well under the 1 MiB / ~15 s limit)
    assert sum(sizes) == int(1.05 * BYTES_PER_S)
    assert all(size % 2 == 0 for size in sizes)


def test_ac47_realtime_pace_then_silence() -> None:
    clock = FakeClock()
    session = FakeSession(clock=clock)
    stop = asyncio.Event()

    async def go() -> None:
        await play_turn(session, _speech(3.0), sleep=clock.sleep)
        speech_count = len(session.sends)
        assert speech_count == 30

        async def sleep_then_stop(seconds: float) -> None:
            await clock.sleep(seconds)
            if len(session.sends) >= speech_count + 5:
                stop.set()

        await stream_silence_until(session, stop, 10.0, sleep=sleep_then_stop)

    asyncio.run(go())
    speech = session.sends[:30]
    silence = session.sends[30:]
    spread = speech[-1].t - speech[0].t
    assert abs(spread - 2.9) <= 0.3  # 3 s of speech sent over ~3 s, never in one burst
    assert len(silence) == 5
    assert all(set(s.pcm or b"x") == {0} for s in silence)  # silence is zero samples
    assert silence[0].t >= speech[-1].t


def test_silence_stops_at_max_seconds() -> None:
    clock = FakeClock()
    session = FakeSession(clock=clock)
    asyncio.run(stream_silence_until(session, asyncio.Event(), 0.5, sleep=clock.sleep))
    assert len(session.sends) == 5


def test_play_turn_returns_send_time_of_last_speech_chunk() -> None:
    clock = FakeClock()
    session = FakeSession(clock=clock)
    last = asyncio.run(play_turn(session, _speech(0.35), sleep=clock.sleep))
    assert last == session.sends[-1].t


def test_ac25_ttfa_from_last_speech_chunk() -> None:
    clock = FakeClock()
    session = FakeSession(clock=clock)
    last = asyncio.run(play_turn(session, _speech(0.5), sleep=clock.sleep))
    # the server answers 400 ms after the last speech chunk; trailing silence must not move it
    delta = AudioDelta(response_id="r1", nbytes=4800, t=last + 0.4)
    assert abs(ttfa_ms(last, delta.t) - 400.0) <= 50.0


# --- barge-in timing (step 17c) -------------------------------------------------------------


class _TwoVoicesTts:
    """Distinct audio per text so the test can find the interrupting chunk."""

    def __init__(self) -> None:
        self.pcm = {
            "Tell me about plans.": b"\x01\x00" * 2400,
            "Stop, one question.": b"\x02\x00" * 2400,
        }

    async def synthesise(self, text: str, voice: str) -> bytes:
        return self.pcm[text]


class _FrozenClock:
    """Every send happens at t=1000.0, so script times are exact offsets from the mark."""

    def __call__(self) -> float:
        return 1000.0

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(0)


def _interrupt_spec(after_ms: int) -> dict:
    raw = make_spec()
    raw["scenarios"][0]["user_turns"] = [
        {"text": "Tell me about plans."},
        {"text": "Stop, one question.", "interrupt_after_assistant_ms": after_ms},
    ]
    return raw


def _run_interrupt(tmp_path: Path, script: list, after_ms: int = 200):
    clock = _FrozenClock()
    spec = preflight(_interrupt_spec(after_ms))
    factory = FakeSessionFactory(script, clock=clock)
    judge = FakeJudge(['{"label": "PASS", "rationale": "r", "evidence": "e"}'])
    audio = TurnAudioSource(_TwoVoicesTts(), tmp_path / "c", tmp_path / "r")
    record = asyncio.run(
        run_gate(spec, sessions=factory, audio=audio, judge=judge, sleep=clock.sleep)
    )
    return record, factory.sessions[0]


def test_ac28_bargein_stop_time(tmp_path: Path) -> None:
    script = [
        AudioDelta("r1", 4800, 1000.05),
        AudioDelta("r1", 4800, 1000.10),  # 200 ms of assistant audio heard: interrupt starts
        AudioDelta("r1", 4800, 1000.25),  # server keeps sending 250 ms after the interrupt mark
        ResponseDone("r1", "cancelled", None, 1000.26),
        AudioDelta("r2", 4800, 1000.50),
        TranscriptDelta("r2", "Sure.", 1000.50),
        ResponseDone("r2", "completed", None, 1000.60),
    ]
    record, session = _run_interrupt(tmp_path, script)
    assert record.cause is None
    first, second = record.turns
    assert (first.bargein_ms, first.bargein_status) == (None, None)
    assert second.bargein_status == "measured"
    assert second.bargein_ms is not None and abs(second.bargein_ms - 250.0) <= 50.0
    assert second.ttfa_ms is not None and abs(second.ttfa_ms - 500.0) <= 50.0
    interrupting = [s for s in session.sends if s.pcm == b"\x02\x00" * 2400]
    assert len(interrupting) == 1  # played once, over the reply, not again afterwards


def test_ac28_reply_too_short_to_interrupt_is_not_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "QUIET_WINDOW_S", 0.05)  # AC-57: r1's turn ends after the window
    script = [
        AudioDelta("r1", 4800, 1000.05),  # only 100 ms before the reply is done
        ResponseDone("r1", "completed", None, 1000.10),
        Delay(0.2),  # longer than the shrunk quiet window: r2 answers the second turn
        AudioDelta("r2", 4800, 1000.50),
        ResponseDone("r2", "completed", None, 1000.60),
    ]
    record, session = _run_interrupt(tmp_path, script)
    second = record.turns[1]
    assert (second.bargein_ms, second.bargein_status) == (None, "not measured")
    assert len([s for s in session.sends if s.pcm == b"\x02\x00" * 2400]) == 1
