# Brief: Higgs Agent Factory

## Goal and audience

Boson's homepage says "Agents that coach themselves." Our harness makes that claim checkable for
any agent you build on Higgs Realtime: you describe the agent, the harness generates it, runs it
through scripted scenarios and interruption tests, and releases it only if it passes. What comes
out is an Eval Card with measured numbers, not a vibe.

The audience is the Boson AI team at the MScAC Higgs Audio hackathon in Toronto. The purpose is
to get noticed by them. A clean, honest demo beats a broad one: one template working end to end
is worth more than five half-working ones.

Track: **Tools and agents**.

Why the eval gate and not the config builder: agentic tasks are where Higgs Realtime is weakest
in independent measurement (see the τ-Voice row in [CLAIMS.md](CLAIMS.md), conversation only).
A builder that refuses to release a failing agent is more useful to Boson than another prompt
editor.

## Timing

Presentations start around 15:00 Toronto time on 2026-10-24
([hackathon page](https://www.boson.ai/blog/mscac-higgs-audio-hackathon-2026)). The schedule is
marked tentative.

## Demo script (3 minutes)

1. **20 s — the problem.** Anyone can spin up a voice agent in an afternoon. Nobody can tell you
   whether it is ready to talk to a customer.
2. **40 s — skills, not one prompt.** Specialist Training is a persona plus five skills, each with
   its own procedure, tools and test scenarios. A brief can also produce a skill proposal before
   any gate run.
3. **60 s — gate and coach.** The v1 card is rejected, 4 of 6, and fails two skills. The judge
   grades every scenario twice and reports its agreement. The coach rewrites only the failing
   skills' procedures, and the re-run gate releases v2 at 6 of 6. The card diff shows what
   changed. Say: one run, one round, and the coach sees the test.
4. **40 s — talk to the agent** (through the Higgs Avatar if it is on). A live conversation, with
   a deliberate interruption mid-sentence.
5. **20 s — what it means for Boson.** "Agents that coach themselves", made measurable; the
   IHBench client PR and the friction log handed over as a gift.

Every number on screen has a row in [CLAIMS.md](CLAIMS.md).

## Priorities

| P | Deliverable | Done when |
|---|---|---|
| P0 | IHBench client for Higgs Realtime, as a PR to `boson-ai/ihbench` | The smoke subset produces a response row per sample with no protocol errors, and the PR is open. Spec: `specs/2026-10-24-ihbench-higgs-client.md`. |
| P1 | Agent Spec + generator + Eval Card for one template (Specialist Training) | The gate runs on the Specialist Training agent and prints an Eval Card from a real run. Spec: `specs/2026-10-24-higgs-agent-factory.md`. |
| P2 | Live demo page | Steps 2 and 3 of the demo run from one page. |
| P3 | Live avatar | The same agent talks through a Higgs Avatar in a LiveKit room (F11). |

If time runs out, stop at the highest finished P. Never ship a half-done higher P over a solid
lower one.

## Success criteria

- The IHBench PR is open against `boson-ai/ihbench`, small, and reproducible from a clean
  checkout with the smoke run its spec defines. Upstream has no CI or test suite to pass.
- One Eval Card, from a real run, shown on stage. Every number on it is traceable.
- The demo runs end to end live, or the recorded fallback plays without apology.
- At least one Boson engineer asks about the gate, the PR or the friction log.

## Non-goals

- Telephony (F9).
- Production auth.
- Multi-user.
- Our own speech-to-speech stack.
- Any marketing claim built on Boson's self-authored benchmarks.

## Fallback

A recorded video of the full 3-minute demo, made as soon as P1 works, kept on the laptop and
not dependent on the venue network.
