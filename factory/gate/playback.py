"""Paced playback of a scripted user turn (service). Real-time pace, then streamed silence.

Boson audio in: only `input_audio_buffer.append`, 24 kHz s16le mono, each event far under
1 MiB base64 (F4). A turn is never sent in one burst (AC-47).
"""

import asyncio
from collections.abc import Awaitable, Callable

from factory.ports import RealtimeSession

CHUNK_MS = 100
_BYTES_PER_MS = 48  # 24 kHz * 2 bytes / 1000 (F4)
CHUNK_BYTES = CHUNK_MS * _BYTES_PER_MS  # 4,800
BYTES_PER_S = 1000 * _BYTES_PER_MS

Sleep = Callable[[float], Awaitable[None]]


async def play_turn(session: RealtimeSession, pcm: bytes, *, sleep: Sleep = asyncio.sleep) -> float:
    """Send `pcm` in 100 ms chunks, one chunk per 100 ms. Returns the send time of the last
    speech chunk (the TTFA start point, AC-25)."""
    last_sent = 0.0
    for start in range(0, len(pcm), CHUNK_BYTES):
        last_sent = await session.send_audio(pcm[start : start + CHUNK_BYTES])
        await sleep(CHUNK_MS / 1000)
    return last_sent


async def stream_silence_until(
    session: RealtimeSession, stop: asyncio.Event, max_s: float, *, sleep: Sleep = asyncio.sleep
) -> None:
    """Keep the input alive with zero samples so server VAD can close the turn, until `stop`
    is set or `max_s` seconds of silence were sent."""
    silence = bytes(CHUNK_BYTES)
    max_chunks = round(max_s * 1000 / CHUNK_MS)
    sent = 0
    while not stop.is_set() and sent < max_chunks:
        await session.send_audio(silence)
        sent += 1
        await sleep(CHUNK_MS / 1000)


def ttfa_ms(last_speech_chunk_t: float, first_audio_delta_t: float) -> float:
    """Client-side TTFA (F17): first `response.output_audio.delta` minus the last speech chunk."""
    return (first_audio_delta_t - last_speech_chunk_t) * 1000.0
