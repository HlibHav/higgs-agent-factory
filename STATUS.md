# Status

Last refreshed: 2026-10-24T15:55:00Z by setup session (Claude Code) — verified by: `uv run pytest -m "not live"` → `4 passed in 0.01s`

## Works now

- Repo conventions are gated offline: `uv run pytest -m "not live"` → `4 passed` (protocol facts carry a source and tag, guard list matches the Check table, `AGENTS.md` symlink, INSIGHTS sections).
- Lint and format are clean: `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `19 files already formatted`.
- Public repo: `gh repo view HlibHav/higgs-agent-factory --json visibility` → `PUBLIC`.
- IHBench fork ready (plan step 0): `git -C /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs branch --list` → `feat/higgs-realtime-client`, `chore/higgs-realtime-client-tests`; `.venv` websockets 17.3, `.venv-ws12` websockets 12.0; upstream push disabled.
- SDD plugins installed at project scope and loaded: `claude plugin list` shows `sdd-engineering` 1.1.1 and `engineering-paved-path`, `research-tools`, `architecture-review` 1.0.1, all enabled.
- A Higgs Realtime text session works end to end: `uv run pytest -m live scripts/smoke.py` connected, got `session.created`, streamed text and `response.done` (`results/smoke-20261024T145225Z.jsonl`). F1, F5 and F14's first ack are VERIFIED-RUN.
- Specs written, both `Status: approved` (Glib, in chat): `specs/2026-10-24-higgs-agent-factory.md` (Full SDD, 53 AC, 15 open non-blocking markers) and `specs/2026-10-24-ihbench-higgs-client.md` (Full SDD, 38 AC, 0 open markers; planned: `docs/plans/2026-10-24-ihbench-higgs-client.md`, Status: ready).

## In progress

- P0: `sdd-engineering:implementer` runs steps 1–7 of `docs/plans/2026-10-24-ihbench-higgs-client.md` in the fork (offline only; main session commits and moves branches).
- P1: `sdd-engineering:implementation-planner` plans `specs/2026-10-24-higgs-agent-factory.md` (multi-agent).

## Blocked

- Opening the draft PR to `boson-ai/ihbench` waits for Glib's OK after the live AC-14 and smoke runs (plan step 8).
- The live smoke test is red by design until F2 is settled: `uv run pytest -m live scripts/smoke.py` → `1 failed` on `assert findings["response_done_usage"] is None`, because the wire returned `usage` while the docs say `null` (F2). Decide whether the smoke should assert the docs claim or the observed behaviour.

## Next

- P0: main session commits the implementer's work test-first, moves code to `feat/higgs-realtime-client` (plan step 7), runs the AC-26 footprint, the live AC-14 harness and the 10-sample smoke (plan step 8), then asks Glib before the draft PR.
- P1: save the agent-factory plan once the planner returns, then run its lanes.
- The first audio-mode gate run records in `docs/boson-protocol.md` whether `usage` arrives in audio mode and whether `input_tokens` includes cached tokens.
- ADR candidates: judge model id (vendor Anthropic decided) and generator model/vendor, each with cost.
