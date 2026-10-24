"""The final render: claims gate, keeper, 180 s cap, graphic files, then segments, audio mix,
loudness normalisation, the caption overlay and the h264 file (AC-37, AC-46, AC-51, AC-52,
AC-57, AC-58, AC-60).

Service layer over `FfmpegPort`. This ffmpeg build has neither `subtitles` nor `drawtext`, so
the captions are a transparent overlay that Remotion renders (`captions.mov` or `captions.webm`
in the graphics folder) and `overlay` lays over the picture.
"""

import json
import re
from pathlib import Path
from typing import Any

from factory.film.claims import ClaimRow, run_claims_gate
from factory.film.ffmpeg_port import FfmpegPort
from factory.film.line_data import LINES_PATH, GraphicId, LineData
from factory.film.run import load_take_events, take_window
from factory.film.stems import StemManifest
from factory.film.take_log import TakeLog
from factory.film.timeline import (
    FPS,
    LEAD_S,
    TAIL_S,
    OverCap,
    TakeWindow,
    build_timeline,
    check_cap,
    graphics_timeline,
    highlight_cues,
    line_start_s,
)

REPO_ROOT = LINES_PATH.parents[2]
TARGET_LUFS = -16.0  # AC-57 (Glib, 2026-10-24)
LUFS_TOL = 0.5  # assumed default
TRUE_PEAK = -1.5
LRA = 11
TONE = (55.0, -22.0)  # AC-56: Hz and dBFS peak, assumed default
TONE_FADE_S = 0.5
WIDTH, HEIGHT = 1920, 1080  # AC-58
_GRAPHIC_OF_BEAT: dict[int, GraphicId] = {1: "hook", 2: "market", 3: "decision"}
GRAPHIC_FILES = {
    "hook": "hook.mp4",
    "market": "market.mp4",
    "decision": "decision.mp4",
    "end-card": "end-card.mp4",
}
CAPTION_FILES = ("captions.mov", "captions.webm")
HIGHLIGHT_COLOUR = "yellow@0.9"
_JSON_BLOCK = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}")


class RenderRefused(Exception):
    """The render did not start (or its result failed a check). `reasons` lists everything."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _frames(seconds: float) -> int:
    return round(seconds * FPS)


def _norm_filter() -> str:
    return (
        f"fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
    )


def build_segment_args(
    source: Path,
    out: Path,
    frames: int,
    *,
    seek_s: float = 0.0,
    still: bool = False,
    extra_filters: list[str] | None = None,
    preset: str = "veryfast",
) -> list[str]:
    """One picture segment of exactly `frames` frames at 1920x1080 and 30 fps. A source that
    ends early repeats its last frame (`tpad`)."""
    pre: list[str] = []
    if still:
        pre = ["-loop", "1", "-framerate", str(FPS)]
    elif seek_s > 0:
        pre = ["-ss", f"{seek_s:.3f}"]
    filters = ["tpad=stop_mode=clone:stop_duration=120", _norm_filter(), *(extra_filters or [])]
    return [
        *pre,
        "-i",
        str(source),
        "-vf",
        ",".join(filters),
        "-an",
        "-frames:v",
        str(frames),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        str(out),
    ]


def build_concat_args(list_file: Path, out: Path) -> list[str]:
    return ["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)]


def build_mix_args(
    stems: list[tuple[Path, float]],
    take: tuple[Path, TakeWindow, float] | None,
    tone_s: float,
    total_s: float,
    out: Path,
) -> list[str]:
    """Narrator stems at their timeline positions (`adelay`), the keeper take's audio over its
    window, and the hook tone, mixed with `amix` (normalize=0). 48 kHz stereo wav."""
    args: list[str] = []
    chains: list[str] = []
    labels: list[str] = []
    fmt = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    for i, (path, start_s) in enumerate(stems):
        args += ["-i", str(path)]
        ms = max(0, round(start_s * 1000))
        chains.append(f"[{i}:a]{fmt},adelay={ms}|{ms}[s{i}]")
        labels.append(f"[s{i}]")
    n = len(stems)
    if take is not None:
        path, window, start_s = take
        args += ["-i", str(path)]
        ms = max(0, round(start_s * 1000))
        chains.append(
            f"[{n}:a]atrim=start={window.start_s:.3f}:end={window.end_s:.3f},"
            f"asetpts=PTS-STARTPTS,{fmt},adelay={ms}|{ms}[take]"
        )
        labels.append("[take]")
        n += 1
    hz, db = TONE
    # `sine` is -18 dBFS peak by default: +18 dB brings it to full scale, then to `db`.
    args += ["-f", "lavfi", "-i", f"sine=frequency={hz:g}:sample_rate=48000:duration={tone_s:.3f}"]
    chains.append(
        f"[{n}:a]volume={db + 18:g}dB,{fmt},afade=t=in:d={TONE_FADE_S},"
        f"afade=t=out:st={max(0.0, tone_s - TONE_FADE_S):.3f}:d={TONE_FADE_S}[tone]"
    )
    labels.append("[tone]")
    chains.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
        f"apad=whole_dur={total_s:.3f},atrim=0:{total_s:.3f}[mix]"
    )
    return [
        *args,
        "-filter_complex",
        ";".join(chains),
        "-map",
        "[mix]",
        "-c:a",
        "pcm_s16le",
        str(out),
    ]


def build_loudnorm_pass1_args(mix: Path) -> list[str]:
    return [
        "-i",
        str(mix),
        "-af",
        f"loudnorm=I={TARGET_LUFS:g}:TP={TRUE_PEAK:g}:LRA={LRA}:print_format=json",
        "-f",
        "null",
        "-",
    ]


def build_loudnorm_pass2_args(mix: Path, out: Path, measured: dict[str, str]) -> list[str]:
    m = measured
    flt = (
        f"loudnorm=I={TARGET_LUFS:g}:TP={TRUE_PEAK:g}:LRA={LRA}:"
        f"measured_I={m['input_i']}:measured_LRA={m['input_lra']}:"
        f"measured_TP={m['input_tp']}:measured_thresh={m['input_thresh']}:"
        f"offset={m['target_offset']}:linear=true:print_format=summary"
    )
    return ["-i", str(mix), "-af", flt, "-ar", "48000", "-c:a", "pcm_s16le", str(out)]


def build_video_args(
    video: Path,
    captions: Path,
    audio: Path,
    out: Path,
    total_frames: int,
    preset: str = "veryfast",
) -> list[str]:
    """Picture + caption overlay + normalised audio -> h264 yuv420p + aac 48 kHz at 30 fps."""
    cap_in = ["-c:v", "libvpx-vp9"] if captions.suffix == ".webm" else []
    return [
        "-i",
        str(video),
        *cap_in,
        "-i",
        str(captions),
        "-i",
        str(audio),
        "-filter_complex",
        "[0:v][1:v]overlay=format=auto:eof_action=pass,format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "2:a",
        "-frames:v",
        str(total_frames),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        "18",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(out),
    ]


def _parse_loudnorm(stderr: str) -> dict[str, str]:
    blocks = _JSON_BLOCK.findall(stderr)
    if not blocks:
        raise RenderRefused(["loudnorm printed no measurement"])
    data = json.loads(blocks[-1])
    return {k: str(v) for k, v in data.items()}


def _concat_list(parts: list[Path], list_file: Path) -> None:
    # Absolute entries: the concat demuxer resolves a relative one against the list's folder.
    lines = [
        f"file '{str(p.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"
        for p in parts
    ]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _find_captions(graphics_dir: Path) -> Path | None:
    return next((graphics_dir / n for n in CAPTION_FILES if (graphics_dir / n).is_file()), None)


async def render_film(
    run_dir: Path,
    graphics_dir: Path,
    *,
    lines: LineData,
    manifest: StemManifest,
    register: dict[str, ClaimRow],
    ffmpeg: FfmpegPort,
    repo_root: Path = REPO_ROOT,
    preset: str = "veryfast",
) -> Path:
    # 1. the claims gate first (AC-46): every failing line, nothing rendered
    gate = run_claims_gate(lines, register)
    if not gate.ok:
        raise RenderRefused([f"{f.line_id}: {f.found!r}: {f.reason}" for f in gate.failures])
    # 2. the keeper (AC-51)
    keeper = TakeLog(run_dir / "takes.jsonl").keeper()
    if keeper is None:
        raise RenderRefused(["no take is marked as the keeper: mark one with the keeper command"])
    events_path = run_dir / f"take-{keeper.take}.events.json"
    if not events_path.is_file():
        raise RenderRefused([f"the keeper take {keeper.take} has no events file {events_path}"])
    t0, events = load_take_events(events_path)
    window = take_window(events, t0)
    if window is None:
        raise RenderRefused([f"the keeper take {keeper.take} has no T1 and T2 events"])
    durations = {r.line_id: r.duration_s for r in manifest.records}
    timeline = build_timeline(lines, durations, window)
    # 3. the 180 s cap (AC-37)
    try:
        check_cap(timeline, lines)
    except OverCap as exc:
        raise RenderRefused(exc.overruns) from exc
    plan = graphics_timeline(timeline, lines)
    # 4. graphic files and the caption overlay (AC-60), 5. the beat 8 images
    problems: list[str] = []
    for slot in plan.graphics:
        path = graphics_dir / GRAPHIC_FILES[slot.id]
        if not path.is_file():
            problems.append(f"graphic beat {slot.id} is missing: {path}")
            continue
        info = await ffmpeg.probe(path)
        if abs(info.frames - slot.frames) > 1:
            problems.append(
                f"graphic beat {slot.id} has {info.frames} frames, its slot needs {slot.frames}"
            )
    captions = _find_captions(graphics_dir)
    if captions is None:
        problems.append(
            f"caption overlay is missing: {' or '.join(CAPTION_FILES)} in {graphics_dir}"
        )
    else:
        info = await ffmpeg.probe(captions)
        if abs(info.frames - plan.total_frames) > 1:
            problems.append(
                f"caption overlay has {info.frames} frames, the film needs {plan.total_frames}"
            )
    beat8 = next(b for b in lines.beats if b.number == 8)
    for image in beat8.images:
        if not (repo_root / image.path).is_file():
            problems.append(f"beat 8 image {image.id} is missing: {image.path}")
    if problems:
        raise RenderRefused(problems)
    assert captions is not None

    # 6. segments
    work = run_dir / "render-work"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []

    async def segment(name: str, source: Path, frames: int, **kwargs: Any) -> None:
        out = work / f"{len(parts):02d}-{name}.mp4"
        await ffmpeg.run(build_segment_args(source, out, frames, preset=preset, **kwargs))
        parts.append(out)

    def graphic_path(graphic_id: str) -> Path:
        return graphics_dir / GRAPHIC_FILES[graphic_id]

    slots = {s.id: s for s in plan.graphics}
    cues = highlight_cues(timeline, lines)
    boxes_path = run_dir / "boxes-b5.json"
    boxes: dict[str, list[float]] = (
        json.loads(boxes_path.read_text(encoding="utf-8")) if boxes_path.is_file() else {}
    )
    for beat in lines.beats:
        slot_t = timeline.beat(beat.number)
        assert slot_t.start_s is not None and slot_t.duration_s is not None
        frames = _frames(slot_t.duration_s)
        if beat.picture == "graphic":
            graphic_id = _GRAPHIC_OF_BEAT[beat.number]
            await segment(beat.id, graphic_path(graphic_id), slots[graphic_id].frames)
        elif beat.picture == "page":
            video = run_dir / f"page-b{beat.number}.video.webm"
            mark = await ffmpeg.first_black(video)
            seek = 0.0 if mark is None else mark[1]
            boxes_filters: list[str] = []
            if beat.number == 5:
                for cue in cues:
                    box = boxes.get(cue.id)
                    if box is None:
                        continue
                    x, y, w, h = box
                    a = cue.start_s - slot_t.start_s
                    b = cue.end_s - slot_t.start_s
                    boxes_filters.append(
                        f"drawbox=x={x:g}:y={y:g}:w={w:g}:h={h:g}:color={HIGHLIGHT_COLOUR}:t=4:"
                        f"enable='between(t,{a:.3f},{b:.3f})'"
                    )
            await segment(beat.id, video, frames, seek_s=seek, extra_filters=boxes_filters)
        elif beat.picture == "take":
            video = run_dir / f"take-{keeper.take}.video.webm"
            mark = await ffmpeg.first_black(video)
            mark_start = 0.0 if mark is None else mark[0]
            # The intro plays over the frames before Start; the take window follows it.
            intro_len = LEAD_S + durations["b7-intro"] + TAIL_S
            seek = max(0.0, mark_start + window.start_s - intro_len)
            await segment(beat.id, video, frames, seek_s=seek)
        else:  # beat 8: two stills, then the end card
            s1 = _frames(slot_t.start_s)
            s2 = _frames(line_start_s(timeline, "b8-s2"))
            s3 = _frames(line_start_s(timeline, "b8-s3"))
            for image, count in ((beat8.images[0], s2 - s1), (beat8.images[1], s3 - s2)):
                await segment(image.id, repo_root / image.path, count, still=True)
            await segment("end-card", graphic_path("end-card"), slots["end-card"].frames)
    # 7. concat
    list_file = work / "segments.txt"
    _concat_list(parts, list_file)
    video_all = work / "video.mp4"
    await ffmpeg.run(build_concat_args(list_file, video_all))

    # 8. audio
    total_s = timeline.total_s
    assert total_s is not None
    stem_by_id = {r.line_id: Path(r.path) for r in manifest.records}
    placed: list[tuple[Path, float]] = [
        (stem_by_id[p.id], p.start_s) for b in timeline.beats for p in b.narration
    ]
    beat7 = timeline.beat(7)
    take_part: tuple[Path, TakeWindow, float] | None = None
    if beat7.take is not None:
        take_part = (run_dir / f"take-{keeper.take}.webm", window, beat7.take.start_s)
    mix = work / "mix.wav"
    hook_s = timeline.beat(1).duration_s or 0.0
    await ffmpeg.run(build_mix_args(placed, take_part, hook_s, total_s, mix))
    # 9. two-pass loudnorm
    measured = _parse_loudnorm(await ffmpeg.run(build_loudnorm_pass1_args(mix)))
    normed = work / "mix-norm.wav"
    await ffmpeg.run(build_loudnorm_pass2_args(mix, normed, measured))
    # 10-11. caption overlay, h264 + aac
    out = run_dir / "film.mp4"
    await ffmpeg.run(build_video_args(video_all, captions, normed, out, plan.total_frames, preset))
    # 12. the result must still meet AC-57 and AC-58
    info = await ffmpeg.probe(out)
    lufs = await ffmpeg.loudness(out)
    bad: list[str] = []
    if (info.width, info.height) != (WIDTH, HEIGHT) or abs(info.fps - FPS) > 0.01:
        bad.append(f"film is {info.width}x{info.height} at {info.fps:g} fps, not 1920x1080 at 30")
    if abs(info.frames - plan.total_frames) > 1:
        bad.append(f"film has {info.frames} frames, the timeline has {plan.total_frames}")
    if abs(lufs - TARGET_LUFS) > LUFS_TOL:
        bad.append(f"film measures {lufs:.1f} LUFS, not {TARGET_LUFS:g} +/- {LUFS_TOL:g}")
    if bad:
        raise RenderRefused(bad)
    return out
