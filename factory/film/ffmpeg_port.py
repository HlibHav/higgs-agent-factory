"""The ffmpeg port: what the render needs from the media tools. Domain types only."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MediaInfo:
    width: int
    height: int
    fps: float
    frames: int
    duration_s: float


class FfmpegPort(Protocol):
    async def run(self, args: list[str]) -> str:
        """Run ffmpeg with `args` (no shell) and return its stderr text. Raises on failure."""
        ...

    async def probe(self, path: Path) -> MediaInfo: ...

    async def loudness(self, path: Path) -> float:
        """Integrated loudness in LUFS (EBU R128)."""
        ...

    async def first_black(self, path: Path) -> tuple[float, float] | None:
        """(start_s, end_s) of the first fully black stretch of the picture, the sync mark."""
        ...
