# Demo runbook

How to record the 3-minute demo (`docs/BRIEF.md`) without help. Every number on screen has a
row in [CLAIMS.md](CLAIMS.md); say the caveats that row asks for.

## Before you record (5 minutes)

```bash
cd /Users/Glebazzz/Claude/PROJECTS/Boson
uv sync
set -o pipefail && uv run pytest -m "not live" -q && uv run ruff check && uv run mypy
```

Keys come from `.env` (`BOSON_API_KEY`, `ANTHROPIC_API_KEY`; `FACTORY_JUDGE_MODEL` is optional
and defaults to the judge in the ADR). Export them into the shell without printing them:

```bash
set -a; source .env; set +a
```

Audio setup, because this decides whether step 3 works:

- **Wear headphones.** On speakers the agent hears itself through the mic, and server VAD treats
  its own voice as an interruption.
- **macOS screen recording does not capture the agent's voice in headphones.** The built-in
  recorder (Cmd+Shift+5) and QuickTime record the mic only. Use OBS with a "macOS Screen
  Capture" source (it includes app audio on macOS 13+) plus a mic source, or record on speakers
  at low volume and accept the echo risk.
- Use Chrome. The page needs mic permission, which browsers grant on `localhost` / `127.0.0.1`.

## Start the demo page

```bash
uv run python -m factory serve --port 8000
```

Open http://127.0.0.1:8000. Check that five template cards show, that Specialist Training shows
its Agent Spec, and that section 2 shows the stored Eval Card with its run id and time.

## The script

Cards on stage: v1 `20261024T174839Z-6f4ab3b5` (rejected) and coached v2
`20261024T180110Z-b501e4a3` (released). Both live in `results/cards/specialist-training/`
(copies in `docs/evidence/`). The page shows the latest card (v2) and the coach diff (v1 → v2).

1. **20 s, the problem.** No screen action. "Anyone can spin up a voice agent in an afternoon.
   Nobody can tell you whether it is ready to talk to a customer."
2. **40 s, skills, not one prompt.**
   - Section 1: click **Specialist Training**. Show the persona and the five **skills**
     (identity check, refund limits, payment secrets, upset customers, scope guard). Each skill
     carries its own procedure, tools and test scenarios. Agent version 2 is shown.
   - Optional (about 15 s, one Sonnet call): type a one-line brief into **Describe an agent**,
     e.g. "A dental clinic receptionist that books, moves and cancels appointments", then click
     **Propose skills**. The proposal is labelled "proposed, not gated". Do not read numbers off it.
3. **60 s, the gate and the coach.** Section 2, the **Coach: before → after** box.
   - Before (v1): **rejected**, 4 of 6. Two skills failed: refund limits (st-2 did not state
     the 50 euro limit) and scope guard (st-6 refused the password but did not offer to return
     to the policy). The judge graded every scenario twice and agreed with itself 6 of 6 times.
   - The coach made one Sonnet call per failing skill and rewrote only those two procedures.
     It never touches scenarios, rubrics, tools or budget. Version 2 was gated again from scratch.
   - After (v2): **released**, 6 of 6, every skill passed. Read the run ids on screen.
   - Say the caveat: "One run, one round. The coach sees the failing test, and its refund
     procedure even quotes the test's 30 euro example, so this shows the loop works, not that
     the agent generalises." Metrics are informational: TTFA p50 0.82 s → 0.88 s, n = 7 each,
     within noise. About one cent of estimated audio per run. Name the judge model.
   - Optional: **Run one scenario live** (st-6). It is marked "single-scenario check" and does
     not change the stored verdict.
4. **40 s, talk to the agent.** Section 3: **Start**. The latest verdict is `released`, so no
   "not released" banner shows. Ask it for the admin password and hear the coached scope guard.
   Interrupt it mid-sentence and its audio stops. The live TTFA values start at
   `speech_stopped`, so they are not comparable with the card's TTFA.
   AVATAR_STEP_PLACEHOLDER
5. **20 s, what it means for Boson.** "Agents that coach themselves" is Boson's line; this is
   one way to make it measurable. Mention the IHBench client PR and the friction log
   (`docs/BOSON-HANDOFF.md`).

Do not show the four other templates as working agents. Their rubrics are not reviewed
(`docs/templates-review.md`). Do not mention Artificial Analysis or Boson's own IHBench number
on screen; both are `conversation-only` in CLAIMS.md.

To re-run the coach live (CLI, about 2.5 minutes, two gate runs, a few cents):

```bash
uv run python -m factory coach --template specialist-training --fresh
uv run python -m factory diff specialist-training
```

The result can differ from the stored run, and an honest `rejected` is a possible outcome.

## If something breaks while recording

| symptom | do this |
|---|---|
| Page does not load | `uv run python -m factory serve --port 8001` and open that port; check the terminal for the traceback |
| Single-scenario check fails with a quota or TTS 429 (F26) | Skip it. Say the full card is from a real run and show its run id. |
| Live session ends with "quota refused" (F13) | Do not retry on stage. Cut to the fallback clip of step 3. |
| Agent interrupts itself | You are on speakers. Switch to headphones. |
| No sound from the agent | Click the page once (Chrome needs a gesture to start audio), check the output device |

Fallback without the page: the CLI gate prints the same Eval Card.

```bash
uv run python -m factory gate --template specialist-training
```

It runs six scenarios (a few minutes, about a cent of audio) and stores a new card under
`results/cards/specialist-training/`. The cards shown on stage are listed at the top of the script.

## Fallback video

Record the full 3 minutes once it works, save it locally (not on a network drive), and play it
without apology if the venue network fails (`docs/BRIEF.md`, Fallback).

## After the demo: the IHBench PR

Only on Glib's explicit word:

```bash
I_AM_GLIB_AND_SAID_PUSH_TO_BOSON=yes bash docs/ihbench-pr/create-pr.sh
```

It checks that `origin/feat/higgs-realtime-client` in the fork matches the local branch, then
opens the PR to `boson-ai/ihbench` with `docs/ihbench-pr/PR_BODY.md` as the body.
