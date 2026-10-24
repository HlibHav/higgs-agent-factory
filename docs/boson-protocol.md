# Boson protocol facts

The one home for what we know about Boson's APIs. Everything else in the repo cites a fact by
its id (`F1`…) and never restates it.

- `VERIFIED-DOCS (date)`: re-read in Boson's docs or site on that date. The docs can be wrong.
- `VERIFIED-RUN (date)`: observed on the wire by `scripts/smoke.py` or a live test on that date.
  Only a live run sets this tag. The evidence column quotes the observed event.
- Anything not in this file is UNVERIFIED. Never fill a gap from the OpenAI Realtime API.

Doc URLs below drop the common prefix `https://docs.boson.ai/`.

## Facts

| id | fact | source | status | evidence |
|---|---|---|---|---|
| F1 | The server sends nothing until the client sends `session.update`; `session.created` then acknowledges that first update. `conversation.created` is never emitted. The model must be named either in `?model=higgs-realtime` on the URL or as `session.model` in the first `session.update`, otherwise that update fails. Endpoint: `wss://api.boson.ai/v1/realtime`. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration · https://docs.boson.ai/models/higgs-realtime/guides/connections-and-sessions | VERIFIED-DOCS (2026-10-24) | Migrate page, "Connection and lifecycle": "Don't wait for `session.created` before configuring the session." |
| F2 | `response.done` carries `usage: null` and `status_details: null` on every response, and `status` is only `completed` or `cancelled`. Token usage, and so billed cost, cannot be read from the API. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration · https://docs.boson.ai/api-reference/realtime/server-events | VERIFIED-DOCS (2026-10-24) | Migrate page, "Responses": `usage` and `status_details` "are currently always `null`". |
| F3 | `conversation.item.create` accepts text only. `input_audio` and `input_image` contents are skipped, `system`-role messages are rejected. User messages use `input_text`, assistant messages use `text` (`output_text` is not recognised). `function_call` and `function_call_output` items work. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration | VERIFIED-DOCS (2026-10-24) | Migrate page, "Events" section. |
| F4 | Audio input goes only through `input_audio_buffer.append`, at most 1 MiB of base64 per event (about 15 s of 24 kHz PCM). Internal processing is 24 kHz, 16-bit, mono PCM. `audio/pcm` accepts 8000/16000/24000/48000 Hz (default 24000); `audio/pcmu` and `audio/opus` also exist. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration · https://docs.boson.ai/models/higgs-realtime/guides/audio-and-voices · https://docs.boson.ai/models/higgs-realtime/guides/connections-and-sessions | VERIFIED-DOCS (2026-10-24) | Connections page: "max ~1 MiB base64 per append, ≈15 s of 24 kHz PCM". |
| F5 | `conversation.item.done`, `rate_limits.updated` and `input_audio_buffer.timeout_triggered` are never emitted. Extra event types exist (`response.output_audio_transcript.length`, `conversation.context.summarized`, `session.idle_timeout`, `session.max_duration_reached`). Clients must tolerate unknown event types. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration | VERIFIED-DOCS (2026-10-24) | Migrate page, "Events": "Don't gate client logic on receiving them." |
| F6 | `output_modalities` is exactly `["audio"]` (default) or `["text"]`. Mixed or empty lists are rejected. Text mode streams `response.output_text.*`. | https://docs.boson.ai/models/higgs-realtime/guides/connections-and-sessions | VERIFIED-DOCS (2026-10-24) | Session configuration table, `output_modalities` row. |
| F7 | Voices: `"default"`, a Boson preset, or `voice_<id>` registered with `POST /v1/audio/voices` (reference audio ≤ 10 MB, ≥ 3.0 s, plus its transcript). Any non-default voice is validated at `session.update`; an unknown voice or an OpenAI voice name fails the update. | https://docs.boson.ai/models/higgs-realtime/guides/audio-and-voices · https://docs.boson.ai/api-reference/audio/create-a-voice | VERIFIED-DOCS (2026-10-24) | Audio page: "an unknown or inaccessible voice fails the update". |
| F8 | `server_vad` threshold defaults to 0.85 (`prefix_padding_ms` 300, `silence_duration_ms` 500, `min_speech_duration` 0.125 s). `create_response`, `interrupt_response` and `eagerness` are accepted but inert; barge-in always interrupts. `idle_timeout_ms` is rejected. After 5 minutes with no detected user speech the server sends `session.idle_timeout` and closes. | https://docs.boson.ai/models/higgs-realtime/guides/turn-detection-and-interruptions · https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration | VERIFIED-DOCS (2026-10-24) | Migrate page, "Session limits": "after 5 minutes without detected user speech". |
| F9 | Transport is WebSocket only. No WebRTC (in progress), no SIP, no `/v1/realtime/calls`, no `output_audio_buffer.*`, no DTMF events. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration | VERIFIED-DOCS (2026-10-24) | Migrate page, "Connection and lifecycle", first bullet. |
| F10 | Tools: `function` tools plus a server-side `web_search` (`{"type": "web_search"}`). A search appears as a `function_call` item named `web_search` with `"executor": "server"`; the client sends no `function_call_output` and no `response.create` for it. Client tools carry `"executor": "client"`. No MCP tools, no tool approvals. | https://docs.boson.ai/models/higgs-realtime/guides/tool-calling · https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration | VERIFIED-DOCS (2026-10-24) | Tool-calling page, "web search" wire section. |
| F11 | Avatar realtime sessions run only in a LiveKit Cloud room (self-hosted is refused with `422 invalid_livekit_url`), are created with `POST /v1/avatar/sessions`, and accept audio only from `transport.publisher_identity` over a LiveKit data stream (24 kHz 16-bit PCM). The LiveKit Agents avatar plugin must be installed from a pinned git commit; the PyPI 1.8.8 release does not work with this API. A first-party LiveKit integration for Realtime is "coming soon". Capacity is limited: `429 capacity_exhausted` with `Retry-After`. | https://docs.boson.ai/models/higgs-avatar/realtime-sessions · https://docs.boson.ai/models/higgs-realtime/integrations/livekit | VERIFIED-DOCS (2026-10-24) | Avatar page: the pin is `warlockee/agents@808a4249850945f91609a9145e50ffea1c9802c4`, a personal fork. |
| F12 | Prices, see the table below. Realtime is billed by tokens; the per-minute audio rates are Boson's estimates for common usage. | https://www.boson.ai/pricing · https://docs.boson.ai/pricing | VERIFIED-DOCS (2026-10-24) | Pricing page: "Actual cost is calculated from tokens consumed." |
| F13 | If billing entitlement is refused mid-session, the server sends an `error` event with `type: "insufficient_quota"` and closes the WebSocket with code `4429`. An invalid or expired ephemeral key closes with code `3000`. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration · https://docs.boson.ai/models/higgs-realtime/guides/connections-and-sessions | VERIFIED-DOCS (2026-10-24) | Migrate page, "Session limits", quota bullet. |

## F12 — price table

Read from boson.ai/pricing on 2026-10-24. These constants live here until the plan decides where
they go in code.

| Product | Billing event | Rate |
|---|---|---|
| Higgs Realtime | Audio input (estimated) | $0.0023 / min |
| Higgs Realtime | Audio output (estimated) | $0.014 / min |
| Higgs Realtime | Input tokens | $0.75 / 1M |
| Higgs Realtime | Cached input tokens | $0.25 / 1M |
| Higgs Realtime | Output tokens | $4.50 / 1M |
| Higgs Realtime | Transcription input (`higgs-stt-3.1`) | $0.0025 / min |
| Higgs TTS 3 | Text input | $0.015 / 1K characters ($15 / 1M) |
| Higgs Avatar | 640×480 or 480×640 (default is 480×640) | $0.07 / min |
| Higgs Avatar | 640×640 | $0.09 / min |

## UNVERIFIED — test before relying

- Whether every `voice_<id>` created through the TTS voices API (F7) works as a Realtime
  `audio.output.voice`, for every voice. The docs say yes; nobody here has seen it.
- Latency when the input is text (`input_text` item plus `response.create`) rather than audio.
- Whether `input_audio_buffer.commit` with `turn_detection: null` behaves as on OpenAI: commit
  creates the user item, and a response starts only on `response.create`.
- Whether the model emits parallel tool calls in one response, and how `response.done` lists
  them.
- How long `session.max_duration_reached` allows (the docs give no number).
