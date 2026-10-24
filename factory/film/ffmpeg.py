"""ffmpeg and ffprobe through `asyncio.create_subprocess_exec` with argv lists: no shell, and
nothing from the environment or a key on the command line. The only place a subprocess starts."""

import asyncio
import json
import re
from pathlib import Path

from factory.film.ffmpeg_port import MediaInfo

_BLACK = re.compile(r"black_start:(?P<s>[\d.]+)\s+black_end:(?P<e>[\d.]+)")
_LUFS = re.compile(r"^\s*I:\s+(?P<v>-?[\d.]+)\s+LUFS", re.MULTILINE)


class FfmpegError(Exception):
    """A media tool failed. The message holds the tail of its stderr."""


class Ffmpeg:
    def __init__(self, binary: str = "ffmpeg", probe_binary: str = "ffprobe") -> None:
        self._binary = binary
        self._probe = probe_binary

    async def _exec(self, argv: list[str]) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    async def run(self, args: list[str]) -> str:
        argv = [self._binary, "-hide_banner", "-nostdin", "-y", *args]
        code, _, err = await self._exec(argv)
        if code != 0:
            raise FfmpegError(f"ffmpeg exited {code}: {err.strip()[-600:]}")
        return err

    async def probe(self, path: Path) -> MediaInfo:
        argv = [
            self._probe,
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
            "-of",
            "json",
            str(path),
        ]
        code, out, err = await self._exec(argv)
        if code != 0:
            raise FfmpegError(f"ffprobe exited {code}: {err.strip()[-300:]}")
        body = json.loads(out)
        stream = body["streams"][0]
        num, _, den = str(stream["r_frame_rate"]).partition("/")
        fps = float(num) / float(den or 1)
        return MediaInfo(
            width=int(stream["width"]),
            height=int(stream["height"]),
            fps=fps,
            frames=int(stream["nb_read_frames"]),
            duration_s=float(body["format"]["duration"]),
        )

    async def loudness(self, path: Path) -> float:
        argv = [
            self._binary,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-af",
            "ebur128=framelog=quiet",
        ]
        code, _, err = await self._exec([*argv, "-f", "null", "-"])
        if code != 0:
            raise FfmpegError(f"ffmpeg exited {code}: {err.strip()[-300:]}")
        found = _LUFS.findall(err)
        if not found:
            raise FfmpegError("no integrated loudness in ffmpeg's report")
        return float(found[-1])

    async def first_black(self, path: Path) -> tuple[float, float] | None:
        argv = [
            self._binary,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-an",
            "-vf",
            "blackdetect=d=0.04:pix_th=0.1",
            "-f",
            "null",
            "-",
        ]
        code, _, err = await self._exec(argv)
        if code != 0:
            raise FfmpegError(f"ffmpeg exited {code}: {err.strip()[-300:]}")
        m = _BLACK.search(err)
        return None if m is None else (float(m["s"]), float(m["e"]))
