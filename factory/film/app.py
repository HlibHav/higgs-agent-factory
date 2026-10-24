"""The film app: the services a CLI command needs, wired by the composition root.

`FilmApp` holds ports only; `factory/composition.py` builds it (`build_film`), so env and
vendor SDKs stay there. `write_timeline` is the one non-trivial service function the CLI uses
besides the services in `stems`, `run` and `render`.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from factory.film.captions import narrator_captions, take_captions
from factory.film.ffmpeg_port import FfmpegPort
from factory.film.line_data import CaptionCue, LineData, Timeline
from factory.film.page_port import CallerPlayed, PageFactory, ServerPort
from factory.film.run import WallClock, load_take_events, take_window
from factory.film.stems import Sleep, StemManifest
from factory.film.take_log import TakeLog
from factory.film.takes import judge_take
from factory.film.timeline import (
    TakeWindow,
    build_timeline,
    graphics_timeline,
    report,
)
from factory.ports import TtsPort

PROVISIONAL_WINDOW = TakeWindow(0.0, 1.0)  # slots do not depend on the take's length


class TimelineUnavailable(Exception):
    """A final timeline needs a keeper take; the message says what is missing."""


@dataclass
class FilmApp:
    tts: TtsPort | None
    model: str
    page_factory: PageFactory | None
    server_factory: Callable[[str], ServerPort]
    ffmpeg: FfmpegPort
    clock: WallClock
    sleep: Sleep = asyncio.sleep
    closers: tuple[Callable[[], Awaitable[None]], ...] = ()

    async def aclose(self) -> None:
        for close in self.closers:
            await close()


def write_timeline(
    out_dir: Path, lines: LineData, manifest: StemManifest, run_id: str | None
) -> tuple[Timeline, list[str], bool]:
    """Write `<out_dir>/timeline.json` and return it with the report lines and whether it is
    final. Without a run it is provisional: the graphic slots and their cues are exact (they do
    not depend on the take) but beats 7 and 8 are not placed, so captions cover beats 1-6 only
    and `total_frames` is not the film's. With a run it uses the keeper take (AC-34, AC-36)."""
    durations = {r.line_id: r.duration_s for r in manifest.records}
    out_dir.mkdir(parents=True, exist_ok=True)
    if run_id is None:
        shadow = build_timeline(lines, durations, PROVISIONAL_WINDOW)
        unknown = build_timeline(lines, durations, None)
        early = [c for c in narrator_captions(shadow, lines) if not c.id.startswith(("b7", "b8"))]
        timeline = graphics_timeline(shadow, lines, early)
        lines_out = report(unknown, lines)
        final = False
    else:
        run_dir = out_dir / "runs" / run_id
        keeper = TakeLog(run_dir / "takes.jsonl").keeper()
        if keeper is None:
            raise TimelineUnavailable(f"run {run_id} has no keeper take: mark one first")
        t0, events = load_take_events(run_dir / f"take-{keeper.take}.events.json")
        window = take_window(events, t0)
        if window is None:
            raise TimelineUnavailable(f"keeper take {keeper.take} has no T1 and T2 events")
        film = build_timeline(lines, durations, window)
        beat7 = film.beat(7)
        assert beat7.take is not None
        offset = beat7.take.start_s - (t0 + window.start_s)  # film seconds = page seconds + this
        t1 = next(e for e in events if isinstance(e, CallerPlayed) and e.line_id == "T1")
        t2 = next((e for e in events if isinstance(e, CallerPlayed) and e.line_id == "T2"), None)
        verdict = judge_take(events, t1, t2)
        captions: list[CaptionCue] = narrator_captions(film, lines)
        captions += take_captions(events, t1, t2, verdict, lines, offset)
        timeline = graphics_timeline(film, lines, captions)
        lines_out = report(film, lines)
        final = True
    (out_dir / "timeline.json").write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
    return timeline, lines_out, final
