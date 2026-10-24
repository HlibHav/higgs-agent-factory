---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: backend
---

# Fall back to a thin WebSocket adapter for the eval gate if pipecat-boson cannot expose the wire

## Context and Problem Statement
`docs/reuse-map.md` says the agent runtime is `pipecat-boson`, not our own Realtime client. The gate must measure TTFA, barge-in stop time and close codes (F13, F21). In 0.1.4 `BosonRealtimeLLMService` sends its own `response.cancel` on barge-in, drops later deltas of that response, and surfaces 4429 / 1013 only as a `push_error` string (`vendor-ref/pipecat-boson/pipecat_boson/realtime/llm.py`). The plan's lane L2 first tries a 30-minute spike: a subclass that taps the raw traffic through private methods.

## Considered Options
- If the spike fails, run the gate through a thin WebSocket adapter shaped like `scripts/smoke.py`, behind the same `RealtimeSession` port; pipecat-boson stays the runtime for the live demo.
- If the spike fails, stop at a P1 without a live gate, keeping the reuse map unchanged.

## Decision Outcome
Chosen option: the thin WebSocket adapter as the pre-approved fallback, because a gate that cannot measure what the Eval Card shows is worse than a small, tested client, and the wire shape is already proven (F1, F14, F23, F24 VERIFIED-RUN). This narrows the reuse map's "do not rebuild a Realtime WebSocket client" for the gate only; the demo runtime remains pipecat-boson.

### Consequences
- Good: no stall at the spike; the gate measures exactly the events the spec defines.
- Bad: a second Realtime client to maintain; the gate and the demo may observe slightly different behaviour.

### Confirmation
L2 reports the spike result; if the fallback is taken, `docs/reuse-map.md` gets a line pointing to this record, and the adapter's offline tests run against the fake Realtime server from lane 0.

## More Information
Plan: `docs/plans/2026-10-24-higgs-agent-factory.md` (step 8, Risks). Related: `docs/reuse-map.md`.
