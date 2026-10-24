"""TTS cache and audio source (steps 13, 13b) and the Boson TTS adapter."""

import asyncio
import json
import wave
from pathlib import Path

import httpx
import pytest

from factory.agent_spec.models import UserTurn
from factory.gate.tts_boson import BosonTts
from factory.gate.tts_cache import AudioMissing, TurnAudioSource
from factory.ports import TtsError
from tests.doubles import FakeTts


def _source(tmp_path: Path, tts: FakeTts) -> TurnAudioSource:
    return TurnAudioSource(tts, tmp_path / "cache", tmp_path / "recordings")


def _write_wav(path: Path, *, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    frames = b"\x07\x00" * 2400 if width == 2 else b"\x07" * 2400
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return frames


def test_ac8_one_request_per_distinct_turn(tmp_path: Path) -> None:
    tts = FakeTts()
    turns = [UserTurn(text="Hello there."), UserTurn(text="What is the price?")]

    async def two_runs() -> list[tuple[bytes, str]]:
        out = []
        for _ in range(2):  # a second run builds a fresh source on the same cache dir
            source = _source(tmp_path, tts)
            for turn in turns:
                out.append(await source.audio_for(turn, "chloe"))
        return out

    results = asyncio.run(two_runs())
    assert len(tts.requests) == 2
    assert {r[1] for r in results} == {"synthesised"}
    assert results[0][0] == results[2][0] == tts.pcm


def test_cache_key_is_text_and_voice(tmp_path: Path) -> None:
    tts = FakeTts()
    source = _source(tmp_path, tts)
    turn = UserTurn(text="Same text")

    async def go() -> None:
        await source.audio_for(turn, "chloe")
        await source.audio_for(turn, "jake")
        await source.audio_for(turn, "chloe")

    asyncio.run(go())
    assert tts.requests == [("Same text", "chloe"), ("Same text", "jake")]
    assert len(list((tmp_path / "cache").glob("*.pcm"))) == 2


def test_failed_synthesis_is_not_cached(tmp_path: Path) -> None:
    tts = FakeTts(fail_texts={"boom"})
    source = _source(tmp_path, tts)
    with pytest.raises(AudioMissing) as info:
        asyncio.run(source.audio_for(UserTurn(text="boom"), "chloe", label="s1 turn 1"))
    assert info.value.turn_label == "s1 turn 1"
    assert not list((tmp_path / "cache").glob("*.pcm"))


def test_ac9_recording_fallback_marked_recorded(tmp_path: Path) -> None:
    tts = FakeTts(fail_texts={"boom"})
    frames = _write_wav(tmp_path / "recordings" / "boom.wav")
    source = _source(tmp_path, tts)
    pcm, kind = asyncio.run(source.audio_for(UserTurn(text="boom", recording="boom.wav"), "chloe"))
    assert kind == "recorded"
    assert pcm == frames


def test_recording_with_wrong_format_is_audio_missing(tmp_path: Path) -> None:
    tts = FakeTts(fail_texts={"boom"})
    _write_wav(tmp_path / "recordings" / "stereo.wav", channels=2)
    _write_wav(tmp_path / "recordings" / "slow.wav", rate=16000)
    source = _source(tmp_path, tts)
    for name in ("stereo.wav", "slow.wav", "absent.wav"):
        turn = UserTurn(text="boom", recording=name)
        with pytest.raises(AudioMissing):
            asyncio.run(source.audio_for(turn, "chloe", label="s1 turn 2"))


def test_recording_path_cannot_escape_recordings_dir(tmp_path: Path) -> None:
    tts = FakeTts(fail_texts={"boom"})
    _write_wav(tmp_path / "secret.wav")
    source = _source(tmp_path, tts)
    (tmp_path / "recordings").mkdir()
    turn = UserTurn(text="boom", recording="../secret.wav")
    with pytest.raises(AudioMissing):
        asyncio.run(source.audio_for(turn, "chloe"))


def test_recording_unused_when_synthesis_works(tmp_path: Path) -> None:
    tts = FakeTts()
    _write_wav(tmp_path / "recordings" / "a.wav")
    source = _source(tmp_path, tts)
    _, kind = asyncio.run(source.audio_for(UserTurn(text="ok", recording="a.wav"), "chloe"))
    assert kind == "synthesised"


# --- Boson TTS adapter (F22) ---------------------------------------------------------------


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, base_url="https://tts.invalid")


def test_boson_tts_request_shape_and_pcm_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"\x01\x00" * 100)

    async def go() -> bytes:
        async with _client(httpx.MockTransport(handler)) as client:
            return await BosonTts(client, "sk-test-key").synthesise("Hi", "chloe")

    assert asyncio.run(go()) == b"\x01\x00" * 100
    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/v1/audio/speech"
    assert request.headers["authorization"] == "Bearer sk-test-key"
    body = json.loads(request.content)
    assert body == {
        "input": "Hi",
        "voice": "chloe",
        "response_format": "pcm",
        "stream": True,
    }  # F22


def test_boson_tts_error_status_raises_without_key_and_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="server blew up")

    async def go() -> None:
        async with _client(httpx.MockTransport(handler)) as client:
            await BosonTts(client, "sk-test-key").synthesise("Hi", "chloe")

    with pytest.raises(TtsError) as info:
        asyncio.run(go())
    assert calls == 1
    assert "500" in str(info.value)
    assert "sk-test-key" not in str(info.value)


def test_boson_tts_transport_error_and_empty_body_raise() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    for handler in (boom, empty):

        async def go(h=handler) -> None:
            async with _client(httpx.MockTransport(h)) as client:
                await BosonTts(client, "sk-test-key").synthesise("Hi", "chloe")

        with pytest.raises(TtsError):
            asyncio.run(go())
