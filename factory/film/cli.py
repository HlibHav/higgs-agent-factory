"""The `factory.film` command line. Entry layer: parse, call one service, print, map refusals to
exit 2 with the message on stderr.

Commands: auditions, stems, timeline, run, keeper, claims, render. Exit codes: 0 done, 1 the run
ended early (blocked request, quota, changed records), 2 a refusal or a bad argument.
"""

import argparse
import asyncio
import re
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from factory.film.app import FilmApp, TimelineUnavailable, write_timeline
from factory.film.audio import StemRejected
from factory.film.claims import CLAIMS_PATH, parse_register, run_claims_gate
from factory.film.guard import RunRefused
from factory.film.line_data import LineData, load_lines
from factory.film.render import RenderRefused, render_film
from factory.film.run import RUN_ID_RE, RunConfig, run_film
from factory.film.stems import (
    StemCache,
    StemFailed,
    StemManifest,
    load_manifest,
    make_auditions,
    make_stems,
)
from factory.film.take_log import KeeperRefused, TakeLog
from factory.film.voices import PresetError

AppFactory = Callable[[Mapping[str, str] | None, Path], FilmApp]


class UsageRefused(Exception):
    """A bad argument or a missing prerequisite; the message says what to do."""


def _is_config_error(exc: Exception) -> bool:
    # `factory.composition.ConfigError` names the missing variable only; the entry maps it
    # without importing the composition root.
    return type(exc).__name__ == "ConfigError"


def _run_id(value: str) -> str:
    if not re.fullmatch(RUN_ID_RE, value):
        raise argparse.ArgumentTypeError(f"not a run id: {value!r}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m factory.film")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("auditions", help="one clip per narrator and caller candidate")
    stems = sub.add_parser("stems", help="generate (or reuse) every narrator, T1 and T2 stem")
    stems.add_argument("--narrator")
    stems.add_argument("--caller")
    timeline = sub.add_parser("timeline", help="write timeline.json and print the report")
    timeline.add_argument("--run", type=_run_id, help="use this run's keeper take (final)")
    run = sub.add_parser("run", help="record the page beats and N takes")
    run.add_argument("--takes", type=int, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--results-dir", type=Path, required=True)
    keeper = sub.add_parser("keeper", help="mark a candidate take as the keeper")
    keeper.add_argument("--run", type=_run_id, required=True)
    keeper.add_argument("--take", type=int, required=True)
    sub.add_parser("claims", help="run the claims gate on lines.json against docs/CLAIMS.md")
    render = sub.add_parser("render", help="render film.mp4 from a run and its graphics")
    render.add_argument("--run", type=_run_id, required=True)
    render.add_argument("--graphics", type=Path, required=True)
    return parser


def _say(text: str) -> None:
    print(text)


def _manifest(out_dir: Path) -> StemManifest:
    manifest = load_manifest(out_dir / "stems")
    if manifest is None:
        raise UsageRefused("no stem manifest: run the `stems` command first")
    return manifest


async def _dispatch(
    args: argparse.Namespace,
    env: Mapping[str, str] | None,
    out_dir: Path,
    app_factory: AppFactory | None,
) -> int:
    lines: LineData = load_lines()
    command: str = args.command

    if command == "claims":
        register = parse_register(CLAIMS_PATH.read_text(encoding="utf-8"))
        result = run_claims_gate(lines, register)
        if not result.ok:
            for f in result.failures:
                print(f"{f.line_id}: {f.found!r}: {f.reason}", file=sys.stderr)
            print(f"claims gate failed: {len(result.failures)} problem(s)", file=sys.stderr)
            return 2
        _say(f"claims gate ok: {len(result.checked)} lines checked")
        return 0

    if command == "timeline":
        try:
            timeline, report, final = write_timeline(out_dir, lines, _manifest(out_dir), args.run)
        except TimelineUnavailable as exc:
            raise UsageRefused(str(exc)) from exc
        for row in report:
            _say(row)
        kind = (
            "final"
            if final
            else "provisional (graphic slots are exact; run `keeper`, then `timeline --run`)"
        )
        _say(f"timeline.json written ({kind}): {timeline.total_frames} frames")
        return 0

    if command == "keeper":
        log = TakeLog(out_dir / "runs" / args.run / "takes.jsonl")
        mark = log.mark_keeper(args.take, lambda: datetime.now(UTC))
        _say(f"keeper: take {mark.take} of run {args.run}")
        return 0

    if app_factory is None:
        raise UsageRefused("no app: start the CLI with `python -m factory.film`")
    app = app_factory(env, out_dir)
    try:
        return await _with_app(args, app, lines, out_dir)
    finally:
        await app.aclose()


async def _with_app(args: argparse.Namespace, app: FilmApp, lines: LineData, out_dir: Path) -> int:
    command: str = args.command
    if command in ("auditions", "stems"):
        if app.tts is None:
            raise UsageRefused("this command needs text-to-speech, which is not configured")
        cache = StemCache(out_dir / "stems", app.tts, app.model, app.sleep)
        if command == "auditions":
            for path in await make_auditions(lines, cache, out_dir / "auditions"):
                _say(str(path))
            return 0
        manifest = await make_stems(lines, args.narrator, args.caller, cache, out_dir / "stems")
        for record in manifest.records:
            state = "cached" if record.reused else "new"
            _say(f"{record.line_id}\t{record.voice}\t{record.duration_s:.2f} s\t{state}")
        return 0

    if command == "run":
        if app.page_factory is None:
            raise UsageRefused("this command needs a browser, which is not configured")
        cfg = RunConfig(args.base_url, args.takes, out_dir, args.results_dir)
        outcome = await run_film(
            cfg,
            page_factory=app.page_factory,
            server=app.server_factory(args.base_url),
            lines=lines,
            manifest=_manifest(out_dir),
            clock=app.clock,
            sleep=app.sleep,
        )
        _say(f"run {outcome.run_id}")
        for e in outcome.entries:
            why = e.reasons if isinstance(e.reasons, str) else ", ".join(e.reasons)
            _say(f"take {e.take}\t{e.status}\t{why}")
        if outcome.stopped:
            print(f"run ended early: {outcome.stopped}", file=sys.stderr)
            return 1
        return 0

    if command == "render":
        register = parse_register(CLAIMS_PATH.read_text(encoding="utf-8"))
        film = await render_film(
            out_dir / "runs" / args.run,
            args.graphics,
            lines=lines,
            manifest=_manifest(out_dir),
            register=register,
            ffmpeg=app.ffmpeg,
        )
        _say(str(film))
        return 0
    raise UsageRefused(f"unknown command {command!r}")


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    out_dir: Path = Path("results/film"),
    app_factory: AppFactory | None = None,
) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:  # argparse already printed the usage error
        return 2 if exc.code else 0
    try:
        return asyncio.run(_dispatch(args, env, out_dir, app_factory))
    except RenderRefused as exc:
        for reason in exc.reasons:
            print(reason, file=sys.stderr)
        print(f"render refused: {len(exc.reasons)} problem(s)", file=sys.stderr)
        return 2
    except KeeperRefused as exc:
        print(f"keeper refused: {'; '.join(exc.reasons)}", file=sys.stderr)
        return 2
    except (RunRefused, PresetError, StemFailed, StemRejected, UsageRefused) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - only the composition root's config error is mapped
        if _is_config_error(exc):
            print(str(exc), file=sys.stderr)
            return 2
        raise
