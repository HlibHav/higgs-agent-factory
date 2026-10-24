# Status

Last refreshed: 2026-10-24T19:05:00Z by the setup session (Claude Code) on `docs/readme-product` — verified by: `uv run pytest -m "not live"` → `274 passed, 1 deselected`; `uv run mypy` → `Success: no issues found in 35 source files` (on `main` at `9e69a68`, pushed).

## New on main (merged 2026-10-24 ~18:12Z, `0faed07`)

- Agent Spec schema 2: persona + skills (procedure, tools, scenarios per skill); all five templates migrated; flat v1 specs still load (AC-70…AC-73).
- Per-skill results on the Eval Card and the page; judge grades every scenario k = 2 times, disagreement never counts as PASS, agreement rate on the card (AC-74, AC-75).
- Coach loop: `uv run python -m factory coach --template specialist-training [--fresh]` — live run: v1 `20261024T174839Z-6f4ab3b5` rejected 4/6 (refund-limits, scope-guard) → v2 `20261024T180110Z-b501e4a3` released 6/6, judge agreement 100% both; one round. Caveat: the coach's refund procedure quotes the test's own example (`factory/INSIGHTS.md`).
- Card diff: `uv run python -m factory diff specialist-training`, and the "Coach: before → after" box on the page (AC-78).
- Skill proposal from a brief on the page, labelled "proposed, not gated" (AC-79); `--caller-voice` for gate/coach (AC-80).
- Higgs Avatar (B′, `livekit-agents==1.8.9`, ADR accepted by Glib): opt-in checkbox in section 3; smoke 201/video/200; server start 3 of 4 OK. Not checked: browser video with a real mic.
- Research: `docs/research/2026-10-24-generator-evals.md` (generator evaluation not implemented).
- Page checked in the built-in browser on port 8012: skills, v2 card with per-skill table, judge agreement, coach diff, avatar checkbox; no console errors.

## Brief agents on the page (merged into `main` as `9e69a68`, pushed)

- Brief agents on the page (AC-81…AC-84). **Propose skills** → **Save as agent and use it** (the server keeps the proposal and refuses server tools) → the "From brief: …" card → **Run full gate** / **Coach failing skills** as background jobs → live talk. Checked in the browser on :8012 with `brief-onboarding-buddy-b948ed`: v1 rejected 5/6 → coach 2 rounds → v3 rejected 5/6 (`docs/CLAIMS.md`).
- Fix: after a mocked tool output the client now sends `response.create` (F29), and the runner waits at most 10 s for the follow-up. Before this, any tool scenario hung the gate. No tool-using template had been live-gated before.
- Avatar: Boson's shared slot pool refused every create from 18:17Z to 18:29Z (`429 capacity_exhausted`, F30). The start now waits up to 20 s for a slot, and the page shows the reason. Not our bug; we cannot see who holds the slots.

## Works now

- P1 live gate, Specialist Training: `uv run python -m factory gate --template specialist-training` → run `20261024T171443Z-35b3f15b` (current code, 17:14Z), `rejected`, 5/6 PASS (st-6 PARTIAL); TTFA p50 748 ms / p95 1,100 ms (n = 7); barge-in 117 ms (n = 1, response ended `cancelled`); estimated audio $0.0118. Card: `docs/evidence/eval-card-20261024T171443Z-35b3f15b.{json,txt}`. Earlier card `20261024T164057Z-9e2ee667` kept in `docs/evidence/`.
- P2 demo page: `uv run python -m factory serve --port 8000` (keys from env, 127.0.0.1 only). Checked in the browser: five template cards, Agent Spec on click, stored Eval Card with run id and timestamp, single-scenario check live (st-1 → PASS, TTFA 740 ms, marked "single-scenario check", stored verdict still REJECTED; checked against the earlier card). Live session checked through `/ws/live/specialist-training` with a scripted client and cached TTS audio: `ready` with `released: false`, assistant audio and transcript returned, live TTFA 499 ms from `speech_stopped`. Not checked by an agent: a real microphone in the browser and barge-in playback stop (AC-42) — Glib checks this with headphones before recording.
- Four more templates (Health Insurance, Fraud Detection, Customer Support, AI Receptionist): AC-3 green offline. Rubrics NOT reviewed by Glib (`docs/templates-review.md`); no live gate run.
- Review loop closed for both plans: `docs/plans/*.state.md`, `docs/plans/*.verify.md`, spec Traceability tables filled. Fixed: AC-29 barge-in counted only for a cancelled response; env read moved to the composition root; IHBench client wraps sends in close handling and bounds the close handshake.
- P0 IHBench client (fork): `feat/higgs-realtime-client` at `abd6bd9`, tests at `0d73f72`; `54 passed` on websockets 17.3 and 12.0; footprint 3 files; both branches pushed to HlibHav/ihbench; the internal draft HlibHav/ihbench#1 is closed as superseded by boson-ai/ihbench#2.
- Protocol: F2 settled (input_tokens includes cached tokens, probe `docs/evidence/probe-usage-20261024T165857Z.json`); F28 new (a cancelled response ends with one `response.done`, status `cancelled`). `scripts/smoke.py` now asserts the wire (usage present).
- Glib's decisions 2026-10-24: composition root on the SDK allow-list (A1 closed); the websockets 12–13 redirect caveat is documented in the PR body; IHBench spec `Status: implemented`; branch merged into `main`.
- Hand-off for Boson: `docs/BOSON-HANDOFF.md`. Demo runbook: `docs/DEMO-RUNBOOK.md`. Upstream PR body and command: `docs/ihbench-pr/` (not run).

- Upstream PR opened by Glib, 2026-10-24: https://github.com/boson-ai/ihbench/pull/2 (from `HlibHav:feat/higgs-realtime-client`); converted back to draft by Glib at 2026-10-24 ~19:10Z (`gh pr ready 2 --undo`). Only Boson's maintainers can merge it.
- Friction findings filed in boson-ai/Boson-Feedback-Collection: issues #40–#45, comments on #18 and #25 (`docs/boson-feedback-filed.md`).
- Product README: draft PR https://github.com/HlibHav/higgs-agent-factory/pull/1 (`docs/readme-product`).
- Worktrees `brief-agents-on-page`, `demo-recording-plan-a0eb9d`, `skills-coach-avatar`: branches merged, no uncommitted changes; `worktree_gc.sh` keeps them (live session / recently touched / no merged PR).

## In progress

- Nothing running.

## Blocked (Glib)

- Record the demo (`docs/DEMO-RUNBOOK.md`). Check the avatar with headphones first.
- Review the four template rubrics before any of them is shown.

## Next

- Token dollar cost (plan steps 21b/21c, AC-50/51) is unblocked by the F2 probe; not built.
- `judge reply invalid` on st-1 (2 of 7 earlier runs) did not recur today; the raw reply is kept in the card when it does (AC-62).
- Review "should" findings left open: `docs/plans/2026-10-24-higgs-agent-factory.verify.md` (S1–S4, C2–C5).
