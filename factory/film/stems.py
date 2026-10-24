"""Film stem cache: one wav per (model, voice, text) with a duration sidecar (AC-11..AC-14),
auditions (AC-8) and the stem manifest.

Service layer: receives a `TtsPort`. The project's own `TurnAudioSource` keys on voice and text
only and stores no duration, so the film keeps its own cache with the same atomic write.
"""

import asyncio
import hashlib
import json
import os
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel

from factory.film.audio import RATE, check_t2
from factory.film.line_data import LineData
from factory.film.voices import StemRequest, audition_requests, check_presets, stem_requests
from factory.ports import TtsError, TtsPort, TtsRateLimited

RETRY_WAITS_S = (2.0, 4.0, 8.0)  # AC-14, F26: no Retry-After header, so a fixed ladder
Sleep = Callable[[float], Awaitable[None]]
MANIFEST_NAME = "manifest.json"


class StemRecord(BaseModel):
    role: str
    line_id: str
    text: str
    voice: str
    model: str
    duration_s: float
    reused: bool
    path: str


class StemManifest(BaseModel):
    narrator: str
    caller: str
    model: str
    records: list[StemRecord]


class StemFailed(Exception):
    """A stem could not be generated. The message names the line (AC-14); no key in it."""

    def __init__(self, line_id: str, reason: str) -> None:
        super().__init__(f"stem for line {line_id} failed: {reason}")
        self.line_id = line_id


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _wav_bytes(pcm: bytes) -> bytes:
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def read_wav_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


class StemCache:
    def __init__(self, cache_dir: Path, tts: TtsPort, model: str, sleep: Sleep = asyncio.sleep):
        self._dir = cache_dir
        self._tts = tts
        self._model = model
        self._sleep = sleep

    @property
    def model(self) -> str:
        return self._model

    def _key(self, req: StemRequest) -> str:
        return hashlib.sha256(f"{self._model}\0{req.voice}\0{req.text}".encode()).hexdigest()

    def _record(self, req: StemRequest, wav_path: Path, duration_s: float, reused: bool):
        return StemRecord(
            role=req.role,
            line_id=req.line_id,
            text=req.text,
            voice=req.voice,
            model=self._model,
            duration_s=duration_s,
            reused=reused,
            path=str(wav_path),
        )

    def _hit(self, req: StemRequest, wav_path: Path) -> StemRecord | None:
        """A hit needs the wav and its sidecar, whole samples and a matching duration."""
        sidecar = wav_path.with_suffix(".json")
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            with wave.open(str(wav_path), "rb") as w:
                if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (RATE, 1, 2):
                    return None
                frames = w.getnframes()
        except (OSError, ValueError, EOFError, wave.Error):
            return None
        if not isinstance(meta, dict) or frames <= 0:
            return None
        duration = meta.get("duration_s")
        same = (meta.get("model"), meta.get("voice"), meta.get("text")) == (
            self._model,
            req.voice,
            req.text,
        )
        if not same or not isinstance(duration, int | float):
            return None
        if abs(duration - frames / RATE) > 1e-6:
            return None
        return self._record(req, wav_path, float(duration), True)

    async def _synthesise(self, req: StemRequest) -> bytes:
        waits = iter(RETRY_WAITS_S)
        while True:
            try:
                pcm = await self._tts.synthesise(req.text, req.voice)
            except TtsRateLimited as exc:
                wait = next(waits, None)
                if wait is None:
                    raise StemFailed(
                        req.line_id, f"TTS refused after {len(RETRY_WAITS_S)} retries (429)"
                    ) from exc
                await self._sleep(wait)
                continue
            except TtsError as exc:
                raise StemFailed(req.line_id, str(exc)) from exc
            if not pcm:
                raise StemFailed(req.line_id, "TTS returned no audio")
            return pcm

    async def get(self, req: StemRequest) -> StemRecord:
        wav_path = self._dir / f"{self._key(req)}.wav"
        hit = self._hit(req, wav_path)
        if hit is not None:
            return hit
        pcm = await self._synthesise(req)
        pcm = pcm[: len(pcm) - len(pcm) % 2]
        duration = (len(pcm) // 2) / RATE
        self._dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(wav_path, _wav_bytes(pcm))  # the wav first, then the sidecar that proves it
        meta = {
            "duration_s": duration,
            "model": self._model,
            "voice": req.voice,
            "text": req.text,
        }
        _atomic_write(wav_path.with_suffix(".json"), json.dumps(meta).encode("utf-8"))
        return self._record(req, wav_path, duration, False)


async def make_auditions(lines: LineData, cache: StemCache, out_dir: Path) -> list[Path]:
    """AC-8: one clip per candidate, `narrator-<preset>.wav` and `caller-<preset>.wav`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for req in audition_requests(lines):
        record = await cache.get(req)
        target = out_dir / f"{req.line_id}.wav"
        _atomic_write(target, Path(record.path).read_bytes())
        written.append(target)
    return written


async def make_stems(
    lines: LineData,
    narrator: str | None,
    caller: str | None,
    cache: StemCache,
    out_dir: Path,
) -> StemManifest:
    """Presets are checked before any TTS call (AC-9, AC-10); T2 must pass `check_t2` (AC-15)."""
    n, c = check_presets(narrator, caller)
    records: list[StemRecord] = []
    for req in stem_requests(lines, n, c):
        record = await cache.get(req)
        if req.line_id == "T2":
            check_t2(read_wav_pcm(Path(record.path)), "T2")
        records.append(record)
    manifest = StemManifest(narrator=n, caller=c, model=cache.model, records=records)
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(out_dir / MANIFEST_NAME, manifest.model_dump_json(indent=2).encode("utf-8"))
    return manifest


def load_manifest(out_dir: Path) -> StemManifest | None:
    try:
        return StemManifest.model_validate_json((out_dir / MANIFEST_NAME).read_text("utf-8"))
    except (OSError, ValueError):
        return None
