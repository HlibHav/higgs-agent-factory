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
from typing import Any

from factory.agent_spec.templates import TEMPLATE_IDS
from factory.composition import ConfigError, build_app
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
    serve = sub.add_parser("serve", help="serve the demo page on 127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


async def _run(app: Any, args: argparse.Namespace) -> int:
    try:
        if args.template:
            result = await app.run_gate_for_template(args.template)
        else:
            result = await app.run_gate_for_brief(args.brief)
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
