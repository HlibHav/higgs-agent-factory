"""Higgs TTS 3 adapter (F22): the only place `httpx` is used for speech."""

import httpx

from factory.ports import TtsError

_SPEECH_PATH = "/v1/audio/speech"  # F22


class BosonTts:
    """`TtsPort` over `POST /v1/audio/speech`. No retry. The key is never logged or put in errors.

    `client` is built by the composition root with the Boson API base URL.
    """

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def synthesise(self, text: str, voice: str) -> bytes:
        # F22: `stream: true` requires `pcm` and yields raw 16-bit / 24 kHz / mono PCM.
        payload = {"input": text, "voice": voice, "response_format": "pcm", "stream": True}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with self._client.stream(
                "POST", _SPEECH_PATH, json=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    raise TtsError(f"TTS request failed with status {response.status_code}")
                pcm = b"".join([chunk async for chunk in response.aiter_bytes()])
        except httpx.HTTPError as exc:
            raise TtsError(f"TTS request failed: {type(exc).__name__}") from exc
        pcm = pcm[: len(pcm) - len(pcm) % 2]  # whole 16-bit samples only
        if not pcm:
            raise TtsError("TTS returned no audio")
        return pcm
