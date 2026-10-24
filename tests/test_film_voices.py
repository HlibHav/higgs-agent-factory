"""Voices and presets (AC-7, AC-9, AC-10, AC-8's request list). Offline, no TTS."""

import pytest

from factory.film.line_data import load_lines
from factory.film.voices import (
    F22_PRESETS,
    NARRATOR_CANDIDATES,
    PresetError,
    audition_requests,
    check_presets,
    stem_requests,
)


def test_presets_named_ok() -> None:
    assert check_presets("nora", "jake") == ("nora", "jake")


def test_voice_outside_f22_refused() -> None:
    with pytest.raises(PresetError, match="alloy"):
        check_presets("alloy", "jake")
    with pytest.raises(PresetError, match="shimmer"):
        check_presets("nora", "shimmer")


def test_missing_presets_name_the_role() -> None:
    with pytest.raises(PresetError, match="narrator"):
        check_presets(None, "jake")
    with pytest.raises(PresetError, match="caller"):
        check_presets("nora", "")


def test_same_preset_twice_refused() -> None:
    with pytest.raises(PresetError, match="two different"):
        check_presets("nora", "nora")


def test_f22_and_candidates() -> None:
    assert F22_PRESETS == ("chloe", "eleanor", "jake", "marcus", "nora", "oliver")
    assert NARRATOR_CANDIDATES == ("eleanor", "nora", "oliver", "marcus")


def test_stem_requests_cover_every_narrator_sentence_and_dialogue() -> None:
    lines = load_lines()
    reqs = stem_requests(lines, "nora", "jake")
    narrator_ids = [n.id for b in lines.beats for n in b.narrator]
    assert [r.line_id for r in reqs if r.role == "narrator"] == narrator_ids
    assert all(r.voice == "nora" for r in reqs if r.role == "narrator")
    caller = [r for r in reqs if r.role == "caller"]
    assert [r.line_id for r in caller] == ["T1", "T2"]
    assert all(r.voice == "jake" for r in caller)
    assert caller[0].text == lines.dialogue[0].text


def test_audition_requests_four_narrator_six_caller() -> None:
    lines = load_lines()
    reqs = audition_requests(lines)
    narr = [r for r in reqs if r.role == "audition" and r.line_id.startswith("narrator-")]
    call = [r for r in reqs if r.role == "audition" and r.line_id.startswith("caller-")]
    assert [r.voice for r in narr] == list(NARRATOR_CANDIDATES)
    assert [r.voice for r in call] == list(F22_PRESETS)
    beat1 = " ".join(n.text for n in lines.beats[0].narrator)
    assert all(r.text == beat1 for r in narr)
    assert all(r.text == lines.dialogue[0].text for r in call)
