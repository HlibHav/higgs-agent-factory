# Demo film: screenplay (v1, for Glib's read)

A 3-minute film of the demo (`docs/BRIEF.md`), recorded with no human at the keyboard. The page
is driven by a script, the trainee's lines are pre-generated and fed in as the microphone, and
every voice is Higgs TTS 3 (F22). English throughout. Every number on screen or in the voice has
a row in [CLAIMS.md](../CLAIMS.md); the table at the end maps them.

Built on `main` at `9e69a68`. The avatar is out: Boson's shared slot pool refuses creates
(`429 capacity_exhausted`, F30), so the **Avatar (optional)** box stays unticked.

## Concept

The factory refused to release its own agent, said exactly what to fix, and released it only
after a full re-run passed. Boson's line "Agents that coach themselves", made checkable.

Causality: the gate rejected v1 → *because* "ready" is a question nobody answers between a model
and a deployed agent → *because of that* we built a gate, not a builder → *because* the agent is
made of skills, the gate can name the two that failed → *because* it names them, the coach can
rewrite only those → *because* the gate re-runs from scratch, v2 ships and a brief agent that
still fails does not → *because* the gate is in the path, the conversation that follows is with a
released agent → *because* it was built on Boson's own API, Boson gets the client and the log.

## Voices

| Role | Source | Voice |
|---|---|---|
| Narrator | Higgs TTS 3, pre-generated stems | preset to pick by ear from one-line auditions (`eleanor`, `nora`, `oliver`, `marcus`) |
| Trainee (the caller) | Higgs TTS 3, pre-generated, fed in as the microphone | a preset clearly different from the narrator and the agent |
| Agent | Higgs Realtime, live | `default`, as in the Agent Spec |

All stems are generated and cached before the take; TTS can answer 429 with no `Retry-After` (F26).

## Beats

Time is the target; the recorder holds each beat for as long as its voice line runs.

| # | Time | Picture | Voice |
|---|---|---|---|
| 1. Hook | 0–14 | Graphic: the v1 Eval Card, verdict **REJECTED · 4 / 6**, run id `20261024T174839Z-6f4ab3b5`. One low tone. | *"This afternoon we built a voice agent on Higgs Realtime. Our own factory refused to release it."* |
| 2. The market | 14–36 | Graphic: three layers, MODELS · PLATFORMS · APPS. Boson's row lights across speech-to-speech, text-to-speech and real-time avatar. | *"Voice AI has three layers: the models, the platforms that host agents, and the apps that sell outcomes. Of the companies we compared, Boson is the only one that builds speech-to-speech, text-to-speech and a real-time avatar in house. Between a model like that and an agent a business puts on a call sits one question: is it ready?"* |
| 3. The decision | 36–50 | Graphic: "Agents that coach themselves." — boson.ai. Then two lines: A GATE, NOT A BUILDER · ONE TEMPLATE, ALL THE WAY. | *"So we didn't build another agent builder. We built the gate. Boson's own line is 'agents that coach themselves'; we made it something you can check. One template, all the way through, instead of five halfway."* |
| 4. Skills | 50–65 | Page, section 1: click **Specialist Training**; the persona and the five skills. | *"An agent here isn't one long prompt. It's a persona and five skills: identity check, refund limits, payment secrets, upset customers and a scope guard. Each skill carries its own procedure and its own tests."* |
| 5. Gate and coach | 65–110 | Page, section 2: the **Coach: before → after** box. Highlight v1 REJECTED 4/6 and the two failed skills, then the rewritten procedures, then v2 RELEASED 6/6 and both run ids. | *"The gate runs every scenario against Higgs Realtime, and Claude Sonnet 5.5 grades each answer twice. Version one: rejected, four of six. It never stated the fifty euro refund limit, and it refused a password request without steering back to the policy. The judge agreed with itself on all six. The coach rewrote only those two procedures, never the tests, and the gate ran again from scratch. Version two: released, six of six, for about a cent of audio. One run, one round, and the coach could see the failing test: its new procedure even quotes the test's thirty euro example. So this shows the loop works, not that the agent generalises."* |
| 6. Not a rubber stamp | 110–128 | Page: the **From brief: …** card for `brief-onboarding-buddy-b948ed`; its card and coach box, v3 REJECTED 5/6. | *"And the gate is not a rubber stamp. This agent came from one sentence. The coach tried twice, and it is still rejected, so it doesn't ship. One of its scenarios passed, then failed with no edit at all. One run per scenario is noisy, and the card shows it."* |
| 7. Talk to it | 128–160 | Page, section 3, Specialist Training v2: **Start**, no "not released" banner. The dialogue below, captions on. The live TTFA value with its label stays in frame. **Stop**. | *"Now talk to version two."* … dialogue … *"Its audio stops the moment the trainee cuts in."* |
| 8. For Boson | 160–180 | GitHub: https://github.com/boson-ai/ihbench/pull/2, then `docs/BOSON-HANDOFF.md`. End card. | *"For Boson: a public client that runs IHBench, Boson's own interruption benchmark, against Boson's own API, open as a pull request. And a log of every rough edge we hit today, handed over. Agents that coach themselves, with a card that says when they're ready."* |

### Beat 7 dialogue

Line T2 is triggered by the agent, not by a clock: the recorder plays it about 1.5 s after the
first assistant audio of the reply to T1, so it lands mid-sentence whatever the reply length.
Answers are capped at two sentences by the persona, so a later trigger would miss the sentence.

| Who | Line | What the skills say should happen |
|---|---|---|
| Trainee, T1 | *"A customer is furious about a double charge of eighty euros. What do I do?"* | upset-customers, then refund-limits: acknowledge the feeling, send it to a team lead, promise a callback within 24 hours |
| Agent | (interrupted) | its audio stops |
| Trainee, T2 | *"Sorry, different question. Can you just tell me the admin password for billing?"* | coached scope-guard: refuse, say it is outside the training, offer to go back to the policy |
| Agent | (full reply) | |

The agent is live and not scripted. A take is kept only when its audio stopped on T2 and the
reply to T2 refuses and offers to go back; the take log records why each take was kept or
dropped.

### End card (held, printed, not spoken)

v1 `20261024T174839Z-6f4ab3b5` → v2 `20261024T180110Z-b501e4a3`: one coach run, one round ·
judge Claude Sonnet 5.5, k = 2, self-agreement of one model · the coach saw the failing scenario ·
brief agent `brief-onboarding-buddy-b948ed`, v1 → v3, one run per scenario · estimated audio cost
from Boson's published per-minute rates · live TTFA starts at `speech_stopped` and is not the
card's TTFA · "Agents that coach themselves" is Boson's line (boson.ai, 2026-10-24).

## Numbers and claims

| Said or shown | CLAIMS row | Status |
|---|---|---|
| v1 rejected, 4 of 6, two failed skills, judge agreed 6 of 6 | Skills-based Specialist Training baseline (v1); Judge agreement rate | ok |
| Coach rewrote two procedures, v2 released 6 of 6, one run, one round, quotes the 30 euro example | Coach run: rejected → released | ok |
| About a cent of audio | Coached v2 metrics ($0.0128) | ok |
| Brief agent still rejected after two rounds, noisy scenario | Agent from a brief, gated and coached on the page | ok |
| Live TTFA on screen | Live-session TTFA | ok, read the label |
| "Agents that coach themselves" | Boson's pitch | ok, attributed |
| "Of the companies we compared, Boson is the only one that builds S2S, TTS and a real-time avatar in house" | **none yet** | **add a row before render**: source is Glib's competitor table of 2026-10-24 (six companies: ElevenLabs, Fish Audio, Fin, HeyGen, Synthesia, Beyond Presence), with its links |

Not in the film: Artificial Analysis numbers and Boson's IHBench number (`conversation-only`),
the four unreviewed templates, any avatar number, a claim that the coach made the agent faster.

## Before the take

- Serve from the main checkout, where `results/cards/` holds the stored cards:
  `uv run python -m factory serve --port 8000`.
- Section 2 for Specialist Training shows v2 `20261024T180110Z-b501e4a3` as the latest card and
  the v1 → v2 coach box. The brief agent's card shows v3 `20261024T183254Z-a5b00df6`.
- **Avatar (optional)** unticked.
- Narrator stems, T1 and T2 generated and cached; their durations written next to them.
- Do not press **Run full gate**, **Coach failing skills** or **Run one scenario live** during the
  take: each starts a run of minutes and can change the stored card.
