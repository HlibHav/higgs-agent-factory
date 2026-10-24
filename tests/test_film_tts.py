"""BosonTts: structured 429 and the model parameter (supports AC-14). httpx.MockTransport only."""

import asyncio

import httpx
import pytest

from factory.gate.tts_boson import TTS_MODEL, BosonTts
from factory.ports import TtsError, TtsRateLimited


def _tts(handler: httpx.MockTransport, model: str | None = None) -> BosonTts:
    client = httpx.AsyncClient(transport=handler, base_url="http://tts.invalid")
    return BosonTts(client, "k-secret") if model is None else BosonTts(client, "k-secret", model)


def test_429_raises_rate_limited() -> None:
    tts = _tts(httpx.MockTransport(lambda r: httpx.Response(429, text="slow down")))
    with pytest.raises(TtsRateLimited) as info:
        asyncio.run(tts.synthesise("hi", "nora"))
    assert isinstance(info.value, TtsError)
    assert "k-secret" not in str(info.value)


def test_500_raises_plain_tts_error() -> None:
    tts = _tts(httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(TtsError) as info:
        asyncio.run(tts.synthesise("hi", "nora"))
    assert not isinstance(info.value, TtsRateLimited)


def test_model_sent() -> None:
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(200, content=b"\x01\x00" * 100)

    tts = _tts(httpx.MockTransport(handler), model="higgs-tts-x")
    asyncio.run(tts.synthesise("hi", "nora"))
    assert b'"model":"higgs-tts-x"' in seen[0].replace(b" ", b"")
    assert tts.model == "higgs-tts-x"


def test_default_model_is_the_constant() -> None:
    assert TTS_MODEL == "higgs-tts-3"
    assert _tts(httpx.MockTransport(lambda r: httpx.Response(200, content=b"\x01\x00"))).model == (
        TTS_MODEL
    )
