"""CLI entry: `python -m factory gate --template specialist-training`, or
`python -m factory serve [--port 8000]` for the demo page (127.0.0.1 only).

Exit codes: 0 when a gate run completed and a card was stored (whatever its verdict, including
`incomplete`; the verdict is printed); 2 for a refusal, abort, spec issues or missing config,
where no card is stored. Keys come from the environment only.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, get_args

from factory.agent_spec.models import UserVoice
from factory.agent_spec.templates import TEMPLATE_IDS
from factory.composition import ConfigError, build_app
from factory.gate.diff import diff_cards, render_diff_text
from factory.gate.records import EvalCard
from factory.gate.render import render_card_text
from factory.gate.runner import GateAborted

DEFAULT_RESULTS_DIR = Path("results")
EXIT_REFUSED = 2
DEFAULT_PORT = 8000
SERVE_HOST = "127.0.0.1"  # a local single-user tool: never bind a public interface

AppFactory = Callable[[Mapping[str, str] | None, Path], Any]
ServerRunner = Callable[..., Any]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m factory")
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("gate", help="run the eval gate and store an Eval Card")
    source = gate.add_mutually_exclusive_group(required=True)
    source.add_argument("--template", choices=TEMPLATE_IDS)
    source.add_argument("--brief", help="free-text brief (max 1,000 characters)")
    gate.add_argument("--caller-voice", choices=get_args(UserVoice))
    coach = sub.add_parser("coach", help="gate, then rewrite failing skills and re-gate")
    coach.add_argument("--template", choices=TEMPLATE_IDS, required=True)
    coach.add_argument("--rounds", type=int, default=2)
    coach.add_argument("--fresh", action="store_true", help="run a new baseline gate first")
    coach.add_argument("--caller-voice", choices=get_args(UserVoice))
    diff = sub.add_parser("diff", help="diff the latest coached card against its parent")
    diff.add_argument("agent_id")
    serve = sub.add_parser("serve", help="serve the demo page on 127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


async def _coach(app: Any, args: argparse.Namespace) -> int:
    try:
        result = await app.coach_template(
            args.template,
            rounds=args.rounds,
            from_latest=not args.fresh,
            caller_voice=args.caller_voice,
        )
    finally:
        await app.aclose()
    if isinstance(result, GateAborted):
        print(result.error_text, file=sys.stderr)
        print("Verdict: not released (no Eval Card stored).", file=sys.stderr)
        return EXIT_REFUSED
    for card in result:
        print(render_card_text(card))
        if card.coach_note:
            print(f"Coach: {card.coach_note}")
    print(render_diff_text(diff_cards(result[0], result[-1])))
    return 0


def _diff(app: Any, args: argparse.Namespace) -> int:
    pair = app.coach_pair(args.agent_id)
    if pair is None:
        print(f"No coached card for {args.agent_id}.", file=sys.stderr)
        return EXIT_REFUSED
    print(render_diff_text(diff_cards(*pair)))
    return 0


async def _run(app: Any, args: argparse.Namespace) -> int:
    try:
        extra = {"caller_voice": args.caller_voice} if args.caller_voice else {}
        if args.template:
            result = await app.run_gate_for_template(args.template, **extra)
        else:
            result = await app.run_gate_for_brief(args.brief, **extra)
    finally:
        await app.aclose()
    if isinstance(result, EvalCard):
        print(render_card_text(result))
        print(f"Stored: {app.last_path}")
        return 0
    if isinstance(result, GateAborted):
        print(result.error_text, file=sys.stderr)
        print("Verdict: not released (no Eval Card stored).", file=sys.stderr)
    else:
        print("The generated spec is invalid.", file=sys.stderr)
        for issue in result:
            print(f"  {issue.field}: {issue.message}", file=sys.stderr)
        print("Verdict: not released (no Eval Card stored).", file=sys.stderr)
    return EXIT_REFUSED


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    app_factory: AppFactory = build_app,
    server_runner: ServerRunner | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        app = app_factory(
            env, results_dir
        )  # None: the composition root reads the process environment
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if args.command == "serve":
        return _serve(app, args.port, server_runner)
    if args.command == "diff":
        return _diff(app, args)
    if args.command == "coach":
        return asyncio.run(_coach(app, args))
    return asyncio.run(_run(app, args))


def _serve(app: Any, port: int, runner: ServerRunner | None) -> int:
    import uvicorn

    from factory.web.app import create_web_app

    run = runner or uvicorn.run
    # `ws="websockets"` pins the implementation: uvicorn's `auto` choice is not documented.
    run(create_web_app(app), host=SERVE_HOST, port=port, ws="websockets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
