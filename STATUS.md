# Status

Last refreshed: 2026-10-24T16:45:00Z by setup session (Claude Code) — verified by: `uv run python -m factory gate --template specialist-training` → `Verdict: rejected`, `Scenarios run: 6, pass rate: 83%` (run `20261024T164057Z-9e2ee667`)

## Works now

- Offline gate on `feat/agent-factory-p1`: `uv run pytest -m "not live" -p no:logging` → `179 passed, 1 deselected, 4 xfailed`; `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `67 files already formatted`.
- P1 live gate, Specialist Training: `uv run python -m factory gate --template specialist-training` (keys in env) → `rejected`, 5/6 PASS, st-6 PARTIAL; TTFA p50 853 ms / p95 1,164 ms (n = 7); barge-in 272 ms (n = 1); one response per turn; estimated audio $0.0116; tokens 2,071 in / 1,840 cached / 155 out. Card copied to `docs/evidence/eval-card-20261024T164057Z-9e2ee667.{json,txt}`.
- Scenario isolation and turn end (AC-55…61): each scenario has its own session; a turn ends after 2 s with no new response; `Responses per turn` is on the card.
- Judge-invalid diagnostics (AC-62…64): an invalid judge reply is kept (≤ 2,000 chars, truncated flag) with the transcript length, in the record and stored card; never rendered.
- P0 IHBench client (fork `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs`): `50 passed` on websockets 17.3 and 12.0; AC-26 footprint = 3 files; live AC-14 replay order MATCH; live smoke `Done. 10 responses saved to responses/higgs-realtime.jsonl, 0 failures.` Internal draft PR: https://github.com/HlibHav/ihbench/pull/1.
- Repo is public: https://github.com/HlibHav/higgs-agent-factory (`main` + `feat/agent-factory-p1`).
- Protocol facts F1–F27 in `docs/boson-protocol.md`; live-verified: F1, F5, F14, F18, F23, F24, F25, F26, F27; F2 is "docs and wire disagree" (usage is reported, audio mode included).

## In progress

- Nothing running.

## Blocked

- The PR to `boson-ai/ihbench` is opened only as the final step, on Glib's word. Until then: HlibHav/ihbench#1.
- The repo's own `uv run pytest -m live scripts/smoke.py` is red by design: it asserts the documented `usage: null`, and the wire returns usage (F2). Glib to decide whether it should assert the docs or the wire.

## Next

- `judge reply invalid` on st-1 happened in 2 of 7 live runs and has not reproduced since; the next occurrence leaves the raw reply in the stored card (AC-62) — read it and record the cause.
- P2 demo page (plan steps 25–28) if wanted; L5 avatar is unplanned.
- Merge `feat/agent-factory-p1` into `main` after review; P0 final PR to Boson when Glib says we're done.
- Measured token dollar cost (plan step 21b) waits on whether `input_tokens` includes cached tokens (F2).
