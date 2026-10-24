---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: backend
---

# Drive the Higgs avatar with livekit-agents 1.8.9 (DataStreamAudioOutput), keep our own runtime

## Context and Problem Statement
The Higgs avatar (F11) runs only in a LiveKit Cloud room and accepts assistant audio from one `publisher_identity` over a LiveKit data stream (24 kHz 16-bit PCM, same as our assistant output). We want an optional avatar on the live-talk page without replacing `run_live`, the Eval Card or the mic WebSocket. The avatar must be off by default, and any avatar failure must leave audio-only live talk working.

## Considered Options
- A. LiveKit Agents worker with the `boson_avatar` plugin pinned to a personal fork (F11): replaces our runtime, needs OpenAI-plugin overrides, bypasses `run_live` and the metrics.
- B. `livekit` + `livekit-api` only, with a hand-built data-stream protocol (`lk.audio_stream`, clear-buffer and playback RPCs): about 179 packages, but we rebuild about 670 lines of `_datastream_io.py` behaviour.
- B'. `livekit-agents==1.8.9` used only for `DataStreamAudioOutput`, plus `livekit-api` for tokens: our runtime stays, one new sink.

## Decision Outcome
Chosen option: B', because it is the smallest change that keeps `run_live` intact and needs no fork (docs: the fork pin applies only to option A). Only `factory/live/avatar_livekit.py` imports livekit; the composition root reads `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`. The browser gets a subscribe-only short-lived token and never a key or secret.

### Consequences
- Good: no runtime replacement, no fork, barge-in maps to `clear_buffer`.
- Bad: 331 packages instead of 179 (pulls onnxruntime, av, numpy, aiohttp); the avatar is billed per minute (F12) and capacity may return `429 capacity_exhausted` (F11). Latency is unmeasured and must not be quoted.
- Licenses: livekit, livekit-api, livekit-agents, livekit-client are Apache-2.0.

### Confirmation
`scripts/avatar_smoke.py` (live, spends cents); offline endpoint tests with doubles; the AC-37 key-leak test covers `LIVEKIT_API_SECRET`.

## More Information
`docs/boson-protocol.md` F11, F12. Research note: avatar-research-and-partial-spec.md (side-session notes, 2026-10-24).
