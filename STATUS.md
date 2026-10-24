# Status

Last refreshed: 2026-10-24T16:10:00Z by setup session (Claude Code) — verified by: `.venv/bin/python scripts/run_inference_api.py --config configs/higgs-realtime.yaml --max-workers 1 --limit 10 --output responses/higgs-realtime.jsonl` (fork) → `Done. 10 responses saved to responses/higgs-realtime.jsonl, 0 failures.`

## Works now

- Repo conventions are gated offline: `uv run pytest -m "not live"` → `4 passed` (protocol facts carry a source and tag, guard list matches the Check table, `AGENTS.md` symlink, INSIGHTS sections).
- Lint and format are clean: `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `19 files already formatted`.
- Public repo: `gh repo view HlibHav/higgs-agent-factory --json visibility` → `PUBLIC`.
- P0 IHBench client, offline: in the fork `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs`, `.venv/bin/python -m pytest tests/test_higgs_realtime_client.py` → `50 passed` (websockets 17.3) and `.venv-ws12/bin/python -m pytest tests/test_higgs_realtime_client.py` → `50 passed` (websockets 12.0).
- P0 PR footprint (AC-26): `git -C …/ihbench-higgs diff --name-only upstream/main...feat/higgs-realtime-client` → exactly `configs/higgs-realtime.yaml`, `ihbench/clients/higgs_realtime_client.py`, `scripts/run_inference_api.py`; runner diff is one changed choices line plus one `elif` block.
- P0 live (AC-14): `tests/live_replay_order.py` → three audio commits, every `previous_item_id` matches, no response before `response.create` (`results/ac14-20261024T153754Z.jsonl`; F24, F25 now VERIFIED-RUN).
- P0 live smoke (AC-28…32): 10 rows, all five keys, all responses non-empty (53–561 chars, 4 interruption types), `0 failures`, 0 `higgs-realtime attempt failed:` lines.
- A Higgs Realtime text session works end to end: `uv run pytest -m live scripts/smoke.py` connected and streamed text (`results/smoke-20261024T145225Z.jsonl`). F1, F5 and F14's first ack are VERIFIED-RUN.
- Specs approved (Glib, in chat): `specs/2026-10-24-ihbench-higgs-client.md` (planned, implemented in the fork) and `specs/2026-10-24-higgs-agent-factory.md` (planned: `docs/plans/2026-10-24-higgs-agent-factory.md`, multi-agent).
- Decisions recorded: `docs/architecture-decisions/` (judge and generator model, dependencies, thin WS fallback for the gate), all accepted by Glib.

## In progress

- Nothing running.

## Blocked

- Opening the draft PR to `boson-ai/ihbench` waits for Glib's explicit OK. Branches are pushed to `HlibHav/ihbench`.
- The repo's own live smoke (`uv run pytest -m live scripts/smoke.py`) is red by design: it asserts the documented `usage: null`, but the wire returned `usage` (F2). Decide whether it should assert the docs claim or the observed behaviour.

## Next

- P0: Glib's OK → open the draft PR from `HlibHav/ihbench:feat/higgs-realtime-client` to `boson-ai/ihbench:main` with the description the plan lists (step 8).
- P1: run lane 0 of `docs/plans/2026-10-24-higgs-agent-factory.md`, then L1, L2 (starts with the 30-minute pipecat tap spike), L3r and L3c in parallel, then J. Glib reviews the Specialist Training rubrics before the stage gate run.
- The first audio-mode gate run records in `docs/boson-protocol.md` whether `usage` arrives in audio mode and whether `input_tokens` includes cached tokens.
