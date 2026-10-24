"""The final render (AC-37, AC-46, AC-51, AC-57, AC-58, AC-60) with real ffmpeg on tiny
generated inputs (`lavfi`), no network. One film is rendered once and shared."""

import asyncio
import inspect
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factory.film import ffmpeg as ffmpeg_module
from factory.film.claims import CLAIMS_PATH, ClaimRow, parse_register
from factory.film.ffmpeg import Ffmpeg
from factory.film.line_data import load_lines
from factory.film.render import (
    GRAPHIC_FILES,
    LUFS_TOL,
    TARGET_LUFS,
    TONE,
    RenderRefused,
    _concat_list,
    build_loudnorm_pass2_args,
    build_mix_args,
    build_video_args,
    render_film,
)
from factory.film.run import RunConfig, load_take_events, run_film, take_window
from factory.film.stems import StemManifest
from factory.film.take_log import TakeLog
from factory.film.timeline import TakeWindow, build_timeline, graphics_timeline
from tests.film_doubles import FakeServer, Sim, build_manifest

LINES = load_lines()
FIXTURE = Path(__file__).parent / "fixtures" / "film" / "claims-2026-10-24.md"
NOW = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
PRESET = "ultrafast"


def _ff(*args: str) -> None:
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr


class RecordingFfmpeg(Ffmpeg):
    def __init__(self) -> None:
        super().__init__()
        self.argv: list[list[str]] = []

    async def run(self, args: list[str]) -> str:
        self.argv.append(list(args))
        return await super().run(args)


@dataclass
class Env:
    base: Path
    run_dir: Path
    graphics: Path
    manifest: StemManifest
    register: dict[str, ClaimRow]
    frames: dict[str, int]
    total_frames: int


def _media(path: Path, *args: str) -> None:
    _ff(*args, str(path))


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Env:
    base = tmp_path_factory.mktemp("render")
    manifest = build_manifest(base / "m", LINES)
    results = base / "results"
    results.mkdir()
    cfg = RunConfig("http://127.0.0.1:8000", 3, base / "out", results)
    sim = Sim()
    outcome = asyncio.run(
        run_film(
            cfg,
            page_factory=sim.factory,
            server=FakeServer(),
            lines=LINES,
            manifest=manifest,
            clock=lambda: NOW,
            sleep=sim.sleep,
        )
    )
    run_dir = base / "out" / "runs" / outcome.run_id
    TakeLog(run_dir / "takes.jsonl").mark_keeper(1, lambda: NOW)
    durations = {r.line_id: r.duration_s for r in manifest.records}
    t0, events = load_take_events(run_dir / "take-1.events.json")
    window = take_window(events, t0)
    assert window is not None
    timeline = build_timeline(LINES, durations, window)
    plan = graphics_timeline(timeline, LINES)
    # media the browser and Remotion would have produced, made with lavfi
    for name in ("page-b4", "page-b5", "page-b6"):
        _media(
            run_dir / f"{name}.video.webm",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=3",
            "-vf",
            "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,0.1,0.2)'",
            "-c:v",
            "libvpx-vp9",
            "-deadline",
            "realtime",
            "-cpu-used",
            "8",
        )
    _media(
        run_dir / "take-1.video.webm",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=640x360:rate=30:duration={window.end_s + 3}",
        "-vf",
        "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,0.1,0.2)'",
        "-c:v",
        "libvpx-vp9",
        "-deadline",
        "realtime",
        "-cpu-used",
        "8",
    )
    _media(
        run_dir / "take-1.webm",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=300:duration={window.end_s + 1}",
        "-af",
        "volume=14dB",
        "-c:a",
        "libopus",
    )
    graphics = base / "graphics"
    graphics.mkdir()
    frames = {s.id: s.frames for s in plan.graphics}
    for slot in plan.graphics:
        _media(
            graphics / GRAPHIC_FILES[slot.id],
            "-f",
            "lavfi",
            "-i",
            "color=c=0x203040:s=640x360:r=30",
            "-frames:v",
            str(slot.frames),
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
        )
    _media(
        graphics / "captions.mov",
        "-f",
        "lavfi",
        "-i",
        "color=c=black@0.0:s=320x180:r=30,format=yuva444p10le",
        "-frames:v",
        str(plan.total_frames),
        "-c:v",
        "prores_ks",
        "-profile:v",
        "4444",
        "-pix_fmt",
        "yuva444p10le",
    )
    for image in LINES.beats[7].images:
        target = base / image.path
        target.parent.mkdir(parents=True, exist_ok=True)
        _media(target, "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=1", "-frames:v", "1")
    return Env(
        base,
        run_dir,
        graphics,
        manifest,
        parse_register(CLAIMS_PATH.read_text(encoding="utf-8")),
        frames,
        plan.total_frames,
    )


def _render(env: Env, **overrides: object) -> Path:
    kwargs: dict[str, object] = {
        "lines": LINES,
        "manifest": env.manifest,
        "register": env.register,
        "ffmpeg": Ffmpeg(),
        "repo_root": env.base,
        "preset": PRESET,
    }
    kwargs.update(overrides)
    run_dir = kwargs.pop("run_dir", env.run_dir)
    graphics = kwargs.pop("graphics", env.graphics)
    return asyncio.run(render_film(run_dir, graphics, **kwargs))  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def film(env: Env) -> tuple[Path, RecordingFfmpeg]:
    recorder = RecordingFfmpeg()
    mp = pytest.MonkeyPatch()
    mp.setenv("BOSON_API_KEY", "sk-fake-key-do-not-leak")
    try:
        out = _render(env, ffmpeg=recorder)
    finally:
        mp.undo()
    return out, recorder


# --- refusals (no media is touched) --------------------------------------------------------


def test_render_refused_on_current_register_lists_market_line(env: Env) -> None:
    old = parse_register(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RenderRefused) as info:
        _render(env, register=old)
    text = " | ".join(info.value.reasons)
    assert "b2-s2" in text and "end-card/market" in text


def test_render_order(env: Env, tmp_path: Path) -> None:
    old = parse_register(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RenderRefused) as info:  # gate fails AND no keeper: only the gate speaks
        _render(env, register=old, run_dir=tmp_path)
    assert all("keeper" not in r for r in info.value.reasons)


def test_render_refused_without_keeper(env: Env, tmp_path: Path) -> None:
    with pytest.raises(RenderRefused, match="keeper"):
        _render(env, run_dir=tmp_path)
    log = TakeLog(tmp_path / "takes.jsonl")
    assert log.keeper() is None and not (tmp_path / "render-work").exists()


def test_185_refused_over_cap(env: Env) -> None:
    long = [
        r.model_copy(update={"duration_s": 200.0}) if r.line_id == "b8-s3" else r
        for r in env.manifest.records
    ]
    with pytest.raises(RenderRefused) as info:
        _render(env, manifest=env.manifest.model_copy(update={"records": long}))
    assert any(r.startswith("total: ") for r in info.value.reasons)
    assert any(r.startswith("beat 8: ") for r in info.value.reasons)


def test_missing_or_short_market_beat_refused(env: Env, tmp_path: Path) -> None:
    graphics = tmp_path / "g"
    shutil.copytree(env.graphics, graphics)
    (graphics / "market.mp4").unlink()
    with pytest.raises(RenderRefused, match="graphic beat market is missing"):
        _render(env, graphics=graphics)
    _media(
        graphics / "market.mp4",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=640x360:r=30",
        "-frames:v",
        str(env.frames["market"] - 5),
        "-pix_fmt",
        "yuv420p",
    )
    with pytest.raises(RenderRefused) as info:
        _render(env, graphics=graphics)
    assert any("graphic beat market has" in r for r in info.value.reasons)
    # one frame off is allowed by the rule, so only the market refusal appears
    assert len([r for r in info.value.reasons if r.startswith("graphic beat")]) == 1


def test_missing_beat8_image_named(env: Env, tmp_path: Path) -> None:
    with pytest.raises(RenderRefused, match="ihbench-pr-2"):
        _render(env, repo_root=tmp_path)


def test_caption_overlay_missing_named(env: Env, tmp_path: Path) -> None:
    graphics = tmp_path / "g"
    shutil.copytree(env.graphics, graphics)
    (graphics / "captions.mov").unlink()
    with pytest.raises(RenderRefused, match="caption overlay is missing"):
        _render(env, graphics=graphics)


# --- the film ------------------------------------------------------------------------------


def test_output_is_1920x1080_30fps(env: Env, film: tuple[Path, RecordingFfmpeg]) -> None:
    out, _ = film
    info = asyncio.run(Ffmpeg().probe(out))
    assert (info.width, info.height) == (1920, 1080)
    assert info.fps == pytest.approx(30.0)
    assert abs(info.frames - env.total_frames) <= 1


def test_mix_measures_minus_16_lufs(film: tuple[Path, RecordingFfmpeg]) -> None:
    out, _ = film
    lufs = asyncio.run(Ffmpeg().loudness(out))
    assert abs(lufs - TARGET_LUFS) <= LUFS_TOL, lufs


def test_argv_has_no_shell_and_no_key(film: tuple[Path, RecordingFfmpeg]) -> None:
    _, recorder = film
    assert recorder.argv
    for args in recorder.argv:
        assert all(isinstance(a, str) for a in args)
        assert not any("sk-fake-key" in a for a in args)
        assert args[0] not in {"sh", "bash", "zsh", "-c"}
    source = inspect.getsource(ffmpeg_module)
    assert "create_subprocess_exec" in source
    assert "create_subprocess_shell" not in source and "shell=True" not in source


def test_segments_and_mix_follow_the_timeline(film: tuple[Path, RecordingFfmpeg]) -> None:
    _, recorder = film
    flat = [" ".join(a) for a in recorder.argv]
    assert any("amix=inputs=" in line and "normalize=0" in line for line in flat)
    assert any("loudnorm" in line and "print_format=json" in line for line in flat)
    assert any("linear=true" in line for line in flat)
    assert any("overlay=format=auto" in line for line in flat)
    assert any("drawbox=" in line and "between(t," in line for line in flat)


# --- pure builders -------------------------------------------------------------------------


def test_build_mix_args_places_stems_take_and_tone(tmp_path: Path) -> None:
    args = build_mix_args(
        [(tmp_path / "a.wav", 0.4), (tmp_path / "b.wav", 1.5)],
        (tmp_path / "t.webm", TakeWindow(2.0, 8.0), 20.0),
        tone_s=11.0,
        total_s=60.0,
        out=tmp_path / "mix.wav",
    )
    graph = args[args.index("-filter_complex") + 1]
    assert (
        "adelay=400|400" in graph and "adelay=1500|1500" in graph and "adelay=20000|20000" in graph
    )
    assert "atrim=start=2.000:end=8.000" in graph
    assert f"volume={TONE[1] + 18:g}dB" in graph and "afade=t=in:d=0.5" in graph
    assert "amix=inputs=4:normalize=0" in graph and "atrim=0:60.000" in graph


def test_build_loudnorm_pass2_is_linear_with_measurements(tmp_path: Path) -> None:
    measured = {
        "input_i": "-20.1",
        "input_lra": "3.0",
        "input_tp": "-5.0",
        "input_thresh": "-31.0",
        "target_offset": "0.2",
    }
    args = build_loudnorm_pass2_args(tmp_path / "m.wav", tmp_path / "o.wav", measured)
    flt = args[args.index("-af") + 1]
    assert (
        "I=-16" in flt and "TP=-1.5" in flt and "measured_I=-20.1" in flt and "linear=true" in flt
    )


def test_build_video_args_overlays_alpha_captions(tmp_path: Path) -> None:
    webm = build_video_args(
        tmp_path / "v.mp4", tmp_path / "c.webm", tmp_path / "a.wav", tmp_path / "f.mp4", 900
    )
    assert "libvpx-vp9" in webm and "libx264" in webm and "aac" in webm
    mov = build_video_args(
        tmp_path / "v.mp4", tmp_path / "c.mov", tmp_path / "a.wav", tmp_path / "f.mp4", 900
    )
    assert "libvpx-vp9" not in mov and mov[mov.index("-frames:v") + 1] == "900"


def test_concat_list_escapes_single_quotes(tmp_path: Path) -> None:
    list_file = tmp_path / "l.txt"
    _concat_list([tmp_path / "it's.mp4"], list_file)
    assert "'\\''" in list_file.read_text()
