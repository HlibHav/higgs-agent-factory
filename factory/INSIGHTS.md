# factory — insights

Insert-only. Format and rules: `engineering-paved-path:engineering-insights` (`reference.md`).

## What Works

- 2026-10-24: A server-VAD barge-in ends the interrupted response `cancelled`, like a client `response.cancel` (F28): live gate `20261024T171443Z-35b3f15b` measured barge-in 117 ms under the AC-29 rule.

- 2026-10-24: The live page proxies browser PCM through one FastAPI WebSocket with a single writer queue; a scripted client with cached TTS audio is a cheap end-to-end check of `/ws/live/<agent>` before touching a mic (`docs/DEMO-RUNBOOK.md`).

## What Doesn't Work

- 2026-10-24: Judging barge-in from the transcript: the transcript arrives whole (F27). Barge-in is measured only when the interrupted response ends `cancelled` (AC-29 fix, `factory/gate/runner.py`).

## Codebase Patterns

- 2026-10-24: Env is read only in `factory/composition.py` (`build_app(None, …)` resolves `os.environ`); entries pass nothing. SDK imports stay in adapters; composition.py is the open exception (finding A1, waiting on Glib).

## Tool & Library Notes

- 2026-10-24: `AsyncAnthropic.messages.create` is overloaded; a Protocol member typed as a read-only property returning `Callable[..., Awaitable[Any]]` satisfies mypy, a plain `async def create(**kwargs)` does not.
- 2026-10-24: pipecat and pipecat-boson ship no type hints; mypy ignores them per module (`pyproject.toml`).

## Recurring Errors & Fixes

## Session Notes

## Open Questions

- 2026-10-24: Does a server-VAD barge-in cancel behave like a client `response.cancel` (F28 covers only the latter)?
