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
2. **60 s — brief → Agent Spec → Eval Card.** Pick the Specialist Training card, show the
   generated Agent Spec, then the full Eval Card from a gate run made before the talk (its run id
   and time on screen): scenario pass rate, IHBench RQ, TTFA p50/p95, barge-in stop time, cost,
   verdict. Run one short scenario live so the room sees the gate is real.
3. **60 s — talk to the agent.** A live conversation, with a deliberate interruption mid-sentence.
   An agent that was not released can still talk, with a visible "not released" label.
4. **40 s — what it means for Boson.** The IHBench client PR that lets Boson's own benchmark run
   against Boson's own API, and the friction log ([FRICTION.md](FRICTION.md)) handed over as a
   gift.

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
