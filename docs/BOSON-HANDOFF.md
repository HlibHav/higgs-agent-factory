# Higgs Realtime: hand-off notes for the Boson team

We are a team at the MScAC Higgs Audio hackathon (Toronto, 2026-10-24) that built an eval gate
for voice agents on Higgs Realtime and a Higgs Realtime client for IHBench. Below is what we hit
along the way, ranked by severity, with the protocol fact ids from our notes
(`docs/boson-protocol.md`) so you can check each one.

Severity: **high** blocks a use case Boson advertises, **medium** costs hours or forces a
workaround, **low** is a papercut. All issues were logged on 2026-10-24.

## Issues

### 1. No path from a phone call to a Realtime session (high)

- **What happened:** Realtime is WebSocket only: no SIP, no WebRTC, no `/v1/realtime/calls`, no
  DTMF events. The solutions page advertises "Automate outbound prospecting" and "Classify
  incoming calls", both phone use cases.
- **Evidence:** F9, VERIFIED-DOCS 2026-10-24.
- **Expected:** a documented path from a phone call to a Realtime session, or a note that
  telephony needs a third-party bridge.
- **Docs:** https://www.boson.ai/solutions ·
  https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration

### 2. TTS 3 rejects a request without `model`, though the docs mark it optional (medium)

- **What happened:** `POST /v1/audio/speech` without `model` returned `400
  invalid_request_error` (pydantic "Field required", loc `model`). The API reference says
  `model` is optional with default `higgs-tts-3`. Adding `"model": "higgs-tts-3"` fixed it. A
  client written from the docs fails on its first call.
- **Evidence:** F26, VERIFIED-RUN 2026-10-24 (docs side: F22).
- **Expected:** docs that match the wire, or the documented default applied server-side.
- **Docs:** https://docs.boson.ai/api-reference/audio/create-a-speech

### 3. TTS 3 returns 429 with no `Retry-After` and no documented limit (medium)

- **What happened:** the speech endpoint answered `429 rate_limit_exceeded` with no
  `Retry-After` header, on the first TTS call of one of our gate runs. The docs give no TTS rate
  limit or window, so a client cannot pace itself.
- **Evidence:** F26, VERIFIED-RUN 2026-10-24 (gate run `20261024T160329Z-aafb9522`).
- **Expected:** a documented limit and a `Retry-After` header. (Avatar already sends one on
  `429 capacity_exhausted`, F11.)
- **Docs:** https://docs.boson.ai/account-billing/usage-and-limits

### 4. IHBench's realtime client does not run against Higgs Realtime (medium)

- **What happened:** `openai_realtime_client.py` waits for `session.created` before sending
  `session.update`, but Higgs sends nothing until the first `session.update` (F1). It sends user
  audio as `input_audio` items and history as `output_text`, which `conversation.item.create`
  skips or does not recognise (F3). It counts `conversation.item.done`, which is never emitted
  (F5). We wrote a separate Higgs client in a fork.
- **Evidence:** F1 VERIFIED-RUN, F5 VERIFIED-RUN for `conversation.item.done`, F3
  VERIFIED-DOCS, all 2026-10-24.
- **Expected:** Boson's own benchmark runs against Boson's own API out of the box.
- **Docs:** https://github.com/boson-ai/ihbench

### 5. The LiveKit avatar plugin is pinned to a personal fork (medium)

- **What happened:** the PyPI 1.8.8 release of the LiveKit Agents avatar plugin does not work
  with the API, and the docs pin a commit on a personal fork,
  `warlockee/agents@808a4249850945f91609a9145e50ffea1c9802c4`.
- **Evidence:** F11, VERIFIED-DOCS 2026-10-24.
- **Expected:** `pip install livekit-plugins-boson-avatar` from a Boson-owned release.
- **Docs:** https://docs.boson.ai/models/higgs-avatar/realtime-sessions

### 6. `response.done` `usage` is documented as always `null`, but it is populated (low)

- **What happened:** the migrate page says `usage` is "currently always `null`". On the wire it
  was populated in text mode and in audio mode, with total, input, output and cached tokens.
  We cannot tell whether it is a supported field to build cost tracking on. The docs also do not
  say whether `input_tokens` includes `cached_tokens`.
- **Evidence:** F2, VERIFIED-RUN 2026-10-24 (`results/smoke-20261024T145225Z.jsonl`, gate run
  `20261024T160618Z-6e8bdda7`).
- **Expected:** docs that match the wire, a statement that `usage` is supported, and the
  inclusion rule for cached tokens.
- **Docs:** https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration

### 7. IHBench's extension point covers local models only (low)

- **What happened:** the README's "two files, zero runner edits" pattern covers local HF
  models. An API backend also needs a `make_client` branch in `scripts/run_inference_api.py`.
- **Evidence:** our IHBench client work, 2026-10-24 (no protocol fact; this is about the repo).
- **Expected:** the documented extension point covers API clients too.
- **Docs:** https://github.com/boson-ai/ihbench

## What worked well

All observed on the wire on 2026-10-24.

- **The session handshake behaves exactly as documented** (F1, F14, F23). Bearer auth on the
  WebSocket handshake opened the session; the server stayed silent until our `session.update`,
  then acknowledged it with `session.created` naming `higgs-realtime`.
- **Manual turns are reliable for scripted replay** (F24, F25). With `turn_detection: null`, no
  response started before our `response.create`, and interleaved text items and audio commits
  kept their order, each `previous_item_id` pointing at the item sent just before. This is what
  made a deterministic IHBench replay possible.
- **Token usage is reported on every response, audio mode included** (F2). Better than the docs
  promise, and enough to put token counts on our Eval Card.
- **The `response.output_audio_transcript.length` extension** (F18) arrives with the matching
  audio length in `length_ms`, alongside the standard `.delta` and `.done` events.
