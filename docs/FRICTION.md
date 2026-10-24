# Friction log (for Boson)

What we hit while building on Boson's public APIs, dated, so it can be handed to the team as is.
Protocol facts are cited by id from [boson-protocol.md](boson-protocol.md).

Severity: `high` blocks a use case Boson advertises · `medium` costs hours or forces a
workaround · `low` is a papercut.

| date | area | what happened | expected | doc link | severity |
|---|---|---|---|---|---|
| 2026-10-24 | Realtime docs | The docs say `response.done` `usage` is "currently always `null`", but a live text-mode response returned `usage` with total, input, output and cached tokens (F2, `results/smoke-20261024T145225Z.jsonl`). A client can't tell whether usage is a supported field to build cost tracking on, or something that may disappear. | Docs that match the wire, and a statement on whether `usage` is reported in audio mode too. | https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration | low |
| 2026-10-24 | Avatar / LiveKit | The LiveKit Agents avatar plugin is not installable from PyPI: the 1.8.8 release does not work with the API, and the docs pin a commit on a personal fork, `warlockee/agents@808a424…` (F11). | `pip install livekit-plugins-boson-avatar` from a Boson-owned release. | https://docs.boson.ai/models/higgs-avatar/realtime-sessions | medium |
| 2026-10-24 | Transport | Realtime is WebSocket only, with no SIP and no WebRTC (F9). The solutions page advertises "Automate outbound prospecting" (Health Insurance) and "Classify incoming calls" (AI Receptionist). | A documented path from a phone call to a Realtime session, or a note that telephony needs a third-party bridge. | https://www.boson.ai/solutions | high |
| 2026-10-24 | IHBench | IHBench's `openai_realtime_client.py` cannot run against Higgs Realtime: it waits for `session.created` before `session.update` (F1), sends user audio as `input_audio` items and history as `output_text` (F3), and counts `conversation.item.done` events (F5). | Boson's own benchmark runs against Boson's own API out of the box. | https://github.com/boson-ai/ihbench | medium |
| 2026-10-24 | IHBench | The README's "two files, zero runner edits" pattern covers local HF models only; an API backend needs a `make_client` branch in `scripts/run_inference_api.py`. | The documented extension point covers API clients too. | https://github.com/boson-ai/ihbench | low |
| 2026-10-24 | TTS 3 docs | `POST /v1/audio/speech` rejects a request without `model` (`400`, pydantic "Field required"), while the API reference marks `model` optional with default `higgs-tts-3` (F26). A client written from the docs fails on its first call. | Docs that match the wire, or the documented default applied server-side. | https://docs.boson.ai/api-reference/audio/create-a-speech | medium |
| 2026-10-24 | TTS 3 limits | The speech endpoint answered `429 rate_limit_exceeded` twice among about eight requests in two minutes, and the docs give no TTS rate limit (F26). We did not capture the 429's headers, so whether `Retry-After` is set is unknown. A client cannot pace itself. | A documented limit and a `Retry-After` header. | https://docs.boson.ai/account-billing/usage-and-limits | medium |
