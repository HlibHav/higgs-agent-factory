"""Audio analysis and the T2 internal-silence refusal (AC-15). F8: server VAD silence 500 ms."""

import pytest

from factory.film.audio import (
    VAD_SILENCE_S,
    StemRejected,
    check_t2,
    internal_silences,
    pcm_duration_s,
)
from tests.film_doubles import silence_pcm, sine_pcm


def test_vad_window_is_500_ms() -> None:
    assert VAD_SILENCE_S == 0.5


def test_pcm_duration() -> None:
    assert pcm_duration_s(sine_pcm(1.25)) == pytest.approx(1.25)


def test_leading_and_trailing_silence_ignored() -> None:
    pcm = silence_pcm(0.8) + sine_pcm(1.0) + silence_pcm(0.9)
    assert internal_silences(pcm) == []
    check_t2(pcm)


def test_t2_internal_gap_refused_and_named() -> None:
    pcm = sine_pcm(1.0) + silence_pcm(0.6) + sine_pcm(0.5)
    with pytest.raises(StemRejected) as info:
        check_t2(pcm)
    assert str(info.value) == "T2 has a 0.60 s silence at 1.00 s"
    assert info.value.line_id == "T2"
    assert info.value.gap_start_s == pytest.approx(1.0)
    assert info.value.gap_s == pytest.approx(0.6)


def test_gap_at_the_window_is_refused_and_below_is_accepted() -> None:
    check_t2(sine_pcm(1.0) + silence_pcm(0.48) + sine_pcm(0.5))
    with pytest.raises(StemRejected):
        check_t2(sine_pcm(1.0) + silence_pcm(0.5) + sine_pcm(0.5))


def test_all_silent_input_has_no_internal_gap_but_is_refused() -> None:
    assert internal_silences(silence_pcm(2.0)) == []
    with pytest.raises(StemRejected, match="silent"):
        check_t2(silence_pcm(2.0))


def test_near_silent_fake_tts_default_reads_as_silence() -> None:
    quiet = b"\x01\x00" * 2400  # the repo's FakeTts default, about -90 dBFS
    with pytest.raises(StemRejected):
        check_t2(quiet)
