"""Audio for scripted user turns: TTS (F22) with a disk cache, recordings as fallback.

Service layer: receives a `TtsPort`; no vendor SDK here.
"""

import hashlib
import os
import wave
from pathlib import Path
from typing import Literal

from factory.agent_spec.models import UserTurn
from factory.ports import TtsError, TtsPort

AudioSourceKind = Literal["synthesised", "recorded"]
_PCM_RATE = 24000  # F4, F22
_PCM_WIDTH = 2  # 16-bit
_PCM_CHANNELS = 1


class AudioMissing(Exception):
    """A scripted turn has neither synthesised nor recorded audio (AC-10)."""

    def __init__(self, turn_label: str, cause: str | None = None) -> None:
        super().__init__(f"no audio for {turn_label}")
        self.turn_label = turn_label
        self.cause = cause  # the key-free `TtsError` text, when synthesis failed


class TurnAudioSource:
    def __init__(self, tts: TtsPort, cache_dir: Path, recordings_dir: Path) -> None:
        self._tts = tts
        self._cache_dir = cache_dir
        self._recordings_dir = recordings_dir

    async def audio_for(
        self, turn: UserTurn, voice: str, *, label: str = "turn"
    ) -> tuple[bytes, AudioSourceKind]:
        """PCM for one scripted turn. `label` ("<scenario_id> turn <n>") names it in errors."""
        cached = self._read_cache(turn.text, voice)
        if cached is not None:
            return cached, "synthesised"
        tts_error: str | None = None
        try:
            pcm = await self._tts.synthesise(turn.text, voice)
        except TtsError as exc:
            pcm = b""
            tts_error = str(exc)
        if pcm:
            self._write_cache(turn.text, voice, pcm)
            return pcm, "synthesised"
        recorded = self._read_recording(turn.recording)
        if recorded is None:
            raise AudioMissing(label, tts_error)
        return recorded, "recorded"

    def _cache_path(self, text: str, voice: str) -> Path:
        digest = hashlib.sha256(f"{voice}\0{text}".encode()).hexdigest()
        return self._cache_dir / f"{digest}.pcm"

    def _read_cache(self, text: str, voice: str) -> bytes | None:
        path = self._cache_path(text, voice)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return data if data and len(data) % _PCM_WIDTH == 0 else None

    def _write_cache(self, text: str, voice: str, pcm: bytes) -> None:
        path = self._cache_path(text, voice)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_bytes(pcm)
        os.replace(tmp, path)  # atomic: a half-written file is never read as a hit

    def _read_recording(self, name: str | None) -> bytes | None:
        if not name or Path(name).name != name or name in {".", ".."}:
            return None
        root = self._recordings_dir.resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            return None
        try:
            with wave.open(str(path), "rb") as wav:
                if (
                    wav.getnchannels() != _PCM_CHANNELS
                    or wav.getsampwidth() != _PCM_WIDTH
                    or wav.getframerate() != _PCM_RATE
                ):
                    return None
                frames = wav.readframes(wav.getnframes())
        except (OSError, EOFError, wave.Error):
            return None
        return frames or None
