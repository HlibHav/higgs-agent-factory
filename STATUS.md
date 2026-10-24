# Status

Last refreshed: 2026-10-24T14:40:00Z by setup session (Claude Code) — verified by: `uv run pytest -m "not live"` → `4 passed in 0.01s`

## Works now

- Repo conventions are gated offline: `uv run pytest -m "not live"` → `4 passed` (protocol facts carry a source and tag, guard list matches the Check table, `AGENTS.md` symlink, INSIGHTS sections).
- Lint and format are clean: `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `15 files already formatted`.
- SDD plugins installed at project scope: `claude plugin list` shows `sdd-engineering` 1.1.1 and `engineering-paved-path`, `research-tools`, `architecture-review` 1.0.1, all enabled.

## In progress

- Specs A (`specs/2026-10-24-higgs-agent-factory.md`) and B (`specs/2026-10-24-ihbench-higgs-client.md`) through `sdd-engineering:spec-creator`.

## Blocked

- Phase 6 live smoke (`scripts/smoke.py`): waiting for `BOSON_API_KEY` in `.env`. Until it runs, every fact in `docs/boson-protocol.md` is `VERIFIED-DOCS` only.
- `../ihbench-higgs` fork: not created; needs Glib's confirmation.

## Next

- Glib sets `Status: approved` on each spec, then `sdd-engineering:implementation-planner` per spec.
