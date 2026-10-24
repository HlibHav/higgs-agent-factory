# Status

Last refreshed: 2026-10-24T17:20:00Z by finalize session (Claude Code) on branch `chore/finalize-hackathon` — verified by: `uv run pytest -m "not live" -q` → `238 passed, 1 deselected`; `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `83 files already formatted`; `uv run mypy` → `Success: no issues found in 30 source files`.

## Works now

- P1 live gate, Specialist Training: `uv run python -m factory gate --template specialist-training` → run `20261024T171443Z-35b3f15b` (current code, 17:14Z), `rejected`, 5/6 PASS (st-6 PARTIAL); TTFA p50 748 ms / p95 1,100 ms (n = 7); barge-in 117 ms (n = 1, response ended `cancelled`); estimated audio $0.0118. Card: `docs/evidence/eval-card-20261024T171443Z-35b3f15b.{json,txt}`. Earlier card `20261024T164057Z-9e2ee667` kept in `docs/evidence/`.
- P2 demo page: `uv run python -m factory serve --port 8000` (keys from env, 127.0.0.1 only). Checked in the browser: five template cards, Agent Spec on click, stored Eval Card with run id and timestamp, single-scenario check live (st-1 → PASS, TTFA 740 ms, marked "single-scenario check", stored verdict still REJECTED; checked against the earlier card). Live session checked through `/ws/live/specialist-training` with a scripted client and cached TTS audio: `ready` with `released: false`, assistant audio and transcript returned, live TTFA 499 ms from `speech_stopped`. Not checked by an agent: a real microphone in the browser and barge-in playback stop (AC-42) — Glib checks this with headphones before recording.
- Four more templates (Health Insurance, Fraud Detection, Customer Support, AI Receptionist): AC-3 green offline. Rubrics NOT reviewed by Glib (`docs/templates-review.md`); no live gate run.
- Review loop closed for both plans: `docs/plans/*.state.md`, `docs/plans/*.verify.md`, spec Traceability tables filled. Fixed: AC-29 barge-in counted only for a cancelled response; env read moved to the composition root; IHBench client wraps sends in close handling and bounds the close handshake.
- P0 IHBench client (fork): `feat/higgs-realtime-client` at `abd6bd9`, tests at `0d73f72`; `54 passed` on websockets 17.3 and 12.0; footprint 3 files; both branches pushed to HlibHav/ihbench (draft PR HlibHav/ihbench#1).
- Protocol: F2 settled (input_tokens includes cached tokens, probe `docs/evidence/probe-usage-20261024T165857Z.json`); F28 new (a cancelled response ends with one `response.done`, status `cancelled`). `scripts/smoke.py` now asserts the wire (usage present).
- Glib's decisions 2026-10-24: composition root on the SDK allow-list (A1 closed); the websockets 12–13 redirect caveat is documented in the PR body; IHBench spec `Status: implemented`; branch merged into `main`.
- Hand-off for Boson: `docs/BOSON-HANDOFF.md`. Demo runbook: `docs/DEMO-RUNBOOK.md`. Upstream PR body and command: `docs/ihbench-pr/` (not run).

## In progress

- Nothing running.

## Blocked (Glib)

- Record the demo (`docs/DEMO-RUNBOOK.md`).
- "Push to Boson": `I_AM_GLIB_AND_SAID_PUSH_TO_BOSON=yes bash docs/ihbench-pr/create-pr.sh`.
- Review the four template rubrics before any of them is shown.

## Next

- Token dollar cost (plan steps 21b/21c, AC-50/51) is unblocked by the F2 probe; not built.
- `judge reply invalid` on st-1 (2 of 7 earlier runs) did not recur today; the raw reply is kept in the card when it does (AC-62).
- Review "should" findings left open: `docs/plans/2026-10-24-higgs-agent-factory.verify.md` (S1–S4, C2–C5).
