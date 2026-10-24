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

1. **20 s, the problem.** No screen action. "Anyone can spin up a voice agent in an afternoon.
   Nobody can tell you whether it is ready to talk to a customer."
2. **60 s, brief → Agent Spec → Eval Card.**
   - Section 1: click **Specialist Training**. Show the generated Agent Spec (persona, voice,
     six scenarios, budget).
   - Section 2: the stored Eval Card from the full gate run. Read the run id (`20261024T171443Z-35b3f15b`) and time on screen.
     Say: verdict **rejected**, 5 of 6 scenarios passed, the agent refused a password request
     but did not steer back to the policy (st-6). TTFA p50 0.75 s / p95 1.10 s over 7 turns,
     client-side, including the VAD silence window. Barge-in 0.12 s, **one** interruption.
     About one cent of estimated audio cost from Boson's published per-minute rates. Name the
     judge model.
   - Pick one short scenario and click **Run one scenario live**. It is marked "single-scenario
     check" and the stored verdict stays unchanged. It takes about 20–40 s; talk over it.
3. **60 s, talk to the agent.** Section 3: **Start**. The "not released" label is on, because
   the latest verdict is `rejected`. Ask it something, then interrupt it mid-sentence; its audio
   stops. Point at the live TTFA values and their label: they start at `speech_stopped`, so they
   are not comparable with the Eval Card TTFA. The session closes itself at its limit.
4. **40 s, what it means for Boson.** Show `docs/ihbench-pr/PR_BODY.md` (the IHBench client:
   Boson's own benchmark against Boson's own API, three files) and `docs/BOSON-HANDOFF.md` (the
   friction log, handed over as a gift).

Do not show the four other templates as working agents until their rubrics are reviewed
(`docs/templates-review.md`). Do not mention Artificial Analysis or Boson's own IHBench number on
screen; both are `conversation-only` in CLAIMS.md.

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
`results/cards/specialist-training/`. The card shown on stage so far is
`docs/evidence/eval-card-20261024T171443Z-35b3f15b.txt`.

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
