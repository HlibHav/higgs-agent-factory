# Status

Last refreshed: 2026-10-24T15:10:00Z by setup session (Claude Code) — verified by: `uv run pytest -m "not live"` → `4 passed in 0.01s`

## Works now

- Repo conventions are gated offline: `uv run pytest -m "not live"` → `4 passed` (protocol facts carry a source and tag, guard list matches the Check table, `AGENTS.md` symlink, INSIGHTS sections).
- Lint and format are clean: `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `18 files already formatted`.
- SDD plugins installed at project scope and loaded: `claude plugin list` shows `sdd-engineering` 1.1.1 and `engineering-paved-path`, `research-tools`, `architecture-review` 1.0.1, all enabled.
- A Higgs Realtime text session works end to end: `uv run pytest -m live scripts/smoke.py` connected, got `session.created`, streamed text and `response.done` (`results/smoke-20261024T145225Z.jsonl`). F1, F5 and F14's first ack are VERIFIED-RUN.
- Specs written, both `Status: draft`: `specs/2026-10-24-higgs-agent-factory.md` (Full SDD, 53 AC, 15 open non-blocking markers) and `specs/2026-10-24-ihbench-higgs-client.md` (Full SDD, 33 AC, 4 open non-blocking markers).

## In progress

- Nothing running.

## Blocked

- The live smoke test is red by design until F2 is settled: `uv run pytest -m live scripts/smoke.py` → `1 failed` on `assert findings["response_done_usage"] is None`, because the wire returned `usage` while the docs say `null` (F2). Decide whether the smoke should assert the docs claim or the observed behaviour.
- `../ihbench-higgs` fork: not created; needs Glib's confirmation.
- Specs wait for Glib to set `Status: approved` before planning.

## Next

- Glib reviews and approves each spec.
- `Use sdd-engineering:implementation-planner on specs/2026-10-24-ihbench-higgs-client.md` (P0) and on `specs/2026-10-24-higgs-agent-factory.md` (P1), each after approval.
- The first audio-mode gate run records in `docs/boson-protocol.md` whether `usage` arrives in audio mode and whether `input_tokens` includes cached tokens.
- ADR candidates: judge model id (vendor Anthropic decided) and generator model/vendor, each with cost.
