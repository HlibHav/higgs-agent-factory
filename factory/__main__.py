"""CLI entry: `python -m factory gate --template specialist-training`.

Exit codes: 0 when a gate run completed and a card was stored (whatever its verdict, including
`incomplete`; the verdict is printed); 2 for a refusal, abort, spec issues or missing config,
where no card is stored. Keys come from the environment only.
"""

import argparse
import asyncio
import os
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

AppFactory = Callable[[Mapping[str, str], Path], Any]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m factory")
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("gate", help="run the eval gate and store an Eval Card")
    source = gate.add_mutually_exclusive_group(required=True)
    source.add_argument("--template", choices=TEMPLATE_IDS)
    source.add_argument("--brief", help="free-text brief (max 1,000 characters)")
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
) -> int:
    args = _parser().parse_args(argv)
    try:
        app = app_factory(os.environ if env is None else env, results_dir)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    return asyncio.run(_run(app, args))


if __name__ == "__main__":
    sys.exit(main())
