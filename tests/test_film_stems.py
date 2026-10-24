"""Stem cache, retry, auditions and manifest (AC-8..AC-14). Offline, doubles only."""

import asyncio
import hashlib
import json
import wave
from pathlib import Path

import pytest

from factory.film.audio import StemRejected
from factory.film.line_data import load_lines
from factory.film.stems import (
    RETRY_WAITS_S,
    StemCache,
    StemFailed,
    load_manifest,
    make_auditions,
    make_stems,
)
from factory.film.voices import PresetError, StemRequest
from tests.film_doubles import BrokenTts, CountingTts, RateLimitedTts, SleepLog, sine_pcm

REQ = StemRequest("narrator", "b1-s1", "Hello there.", "nora")
MODEL = "higgs-tts-3"


def _cache(tmp_path: Path, tts: object, sleep: SleepLog | None = None) -> StemCache:
    return StemCache(tmp_path / "stems", tts, MODEL, sleep or SleepLog())  # type: ignore[arg-type]


def test_same_stem_twice_one_request(tmp_path: Path) -> None:
    tts = CountingTts()
    cache = _cache(tmp_path, tts)
    first = asyncio.run(cache.get(REQ))
    second = asyncio.run(cache.get(REQ))
    assert len(tts.requests) == 1
    assert (first.reused, second.reused) == (False, True)
    assert first.path == second.path


def test_text_voice_model_change_new_stem_old_kept(tmp_path: Path) -> None:
    tts = CountingTts()
    cache = _cache(tmp_path, tts)
    a = asyncio.run(cache.get(REQ))
    b = asyncio.run(cache.get(StemRequest("narrator", "b1-s1", "Hello there!", "nora")))
    c = asyncio.run(cache.get(StemRequest("narrator", "b1-s1", "Hello there.", "oliver")))
    other_model = StemCache(tmp_path / "stems", tts, "higgs-tts-4", SleepLog())  # type: ignore[arg-type]
    d = asyncio.run(other_model.get(REQ))
    assert len({a.path, b.path, c.path, d.path}) == 4
    assert all(Path(p).exists() for p in (a.path, b.path, c.path, d.path))
    assert len(tts.requests) == 4


def test_cache_hit_requires_matching_model(tmp_path: Path) -> None:
    tts = CountingTts()
    first = asyncio.run(_cache(tmp_path, tts).get(REQ))
    sidecar = Path(first.path).with_suffix(".json")
    data = json.loads(sidecar.read_text())
    data["model"] = "someone-else"
    sidecar.write_text(json.dumps(data))
    asyncio.run(_cache(tmp_path, tts).get(REQ))
    assert len(tts.requests) == 2


def test_duration_recorded_next_to_stem(tmp_path: Path) -> None:
    rec = asyncio.run(_cache(tmp_path, CountingTts(seconds=0.75)).get(REQ))
    wav = Path(rec.path)
    sidecar = json.loads(wav.with_suffix(".json").read_text())
    assert sidecar["duration_s"] == pytest.approx(0.75)
    assert rec.duration_s == pytest.approx(0.75)
    with wave.open(str(wav), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
        assert w.getnframes() == 18000
    key = hashlib.sha256(f"{MODEL}\0nora\0Hello there.".encode()).hexdigest()
    assert wav.name == f"{key}.wav"


def test_half_written_stem_is_not_a_hit(tmp_path: Path) -> None:
    tts = CountingTts()
    first = asyncio.run(_cache(tmp_path, tts).get(REQ))
    Path(first.path).with_suffix(".json").unlink()
    again = asyncio.run(_cache(tmp_path, tts).get(REQ))
    assert len(tts.requests) == 2
    assert again.reused is False
    assert Path(again.path).with_suffix(".json").exists()


def test_sidecar_duration_must_match_the_wav(tmp_path: Path) -> None:
    tts = CountingTts()
    first = asyncio.run(_cache(tmp_path, tts).get(REQ))
    sidecar = Path(first.path).with_suffix(".json")
    data = json.loads(sidecar.read_text())
    data["duration_s"] = 9.0
    sidecar.write_text(json.dumps(data))
    asyncio.run(_cache(tmp_path, tts).get(REQ))
    assert len(tts.requests) == 2


def test_429_retries_2_4_8_then_named_stop_no_stem(tmp_path: Path) -> None:
    tts = RateLimitedTts(fail_times=99)
    sleep = SleepLog()
    cache = _cache(tmp_path, tts, sleep)
    with pytest.raises(StemFailed) as info:
        asyncio.run(cache.get(REQ))
    assert RETRY_WAITS_S == (2.0, 4.0, 8.0)
    assert sleep.waits == [2.0, 4.0, 8.0]
    assert len(tts.requests) == 4
    assert "b1-s1" in str(info.value) and info.value.line_id == "b1-s1"
    assert list((tmp_path / "stems").glob("*")) == []  # no partial stem


def test_429_then_success_within_retries(tmp_path: Path) -> None:
    tts = RateLimitedTts(fail_times=3)
    sleep = SleepLog()
    rec = asyncio.run(_cache(tmp_path, tts, sleep).get(REQ))
    assert len(tts.requests) == 4 and sleep.waits == [2.0, 4.0, 8.0]
    assert Path(rec.path).exists()


def test_other_tts_error_is_not_retried(tmp_path: Path) -> None:
    tts = BrokenTts()
    sleep = SleepLog()
    with pytest.raises(StemFailed, match="b1-s1"):
        asyncio.run(_cache(tmp_path, tts, sleep).get(REQ))
    assert len(tts.requests) == 1 and sleep.waits == []


def test_auditions_four_narrator_six_caller_named_by_preset(tmp_path: Path) -> None:
    lines = load_lines()
    tts = CountingTts()
    paths = asyncio.run(make_auditions(lines, _cache(tmp_path, tts), tmp_path / "aud"))
    names = sorted(p.name for p in paths)
    assert names == sorted(
        [f"narrator-{p}.wav" for p in ("eleanor", "nora", "oliver", "marcus")]
        + [f"caller-{p}.wav" for p in ("chloe", "eleanor", "jake", "marcus", "nora", "oliver")]
    )
    assert all(p.exists() for p in paths)
    assert len(tts.requests) == 10


def _refused(tmp_path: Path, narrator: str | None, caller: str | None) -> tuple[Exception, int]:
    tts = CountingTts()
    with pytest.raises(PresetError) as info:
        asyncio.run(
            make_stems(load_lines(), narrator, caller, _cache(tmp_path, tts), tmp_path / "out")
        )
    return info.value, len(tts.requests)


def test_missing_caller_preset_refused_zero_tts(tmp_path: Path) -> None:
    error, requests = _refused(tmp_path, "nora", None)
    assert "caller" in str(error) and requests == 0
    error, requests = _refused(tmp_path, None, "jake")
    assert "narrator" in str(error) and requests == 0


def test_same_preset_twice_refused_zero_tts(tmp_path: Path) -> None:
    error, requests = _refused(tmp_path, "nora", "nora")
    assert "different" in str(error) and requests == 0


def test_voice_outside_f22_refused_zero_tts(tmp_path: Path) -> None:
    error, requests = _refused(tmp_path, "nora", "alloy")
    assert "alloy" in str(error) and requests == 0


def test_manifest_lists_every_narrator_t1_t2(tmp_path: Path) -> None:
    lines = load_lines()
    out = tmp_path / "out"
    manifest = asyncio.run(make_stems(lines, "nora", "jake", _cache(tmp_path, CountingTts()), out))
    narr = [n.id for b in lines.beats for n in b.narrator]
    assert [r.line_id for r in manifest.records] == [*narr, "T1", "T2"]
    assert (manifest.narrator, manifest.caller, manifest.model) == ("nora", "jake", MODEL)
    loaded = load_manifest(out)
    assert loaded == manifest
    assert load_manifest(tmp_path / "nowhere") is None


def test_t2_with_internal_gap_refused(tmp_path: Path) -> None:
    gappy = sine_pcm(1.0) + b"\x00\x00" * 14400 + sine_pcm(0.5)
    tts = CountingTts(pcm_for=lambda text: gappy if text.startswith("Sorry") else sine_pcm(0.3))
    with pytest.raises(StemRejected, match="T2"):
        asyncio.run(make_stems(load_lines(), "nora", "jake", _cache(tmp_path, tts), tmp_path / "o"))
