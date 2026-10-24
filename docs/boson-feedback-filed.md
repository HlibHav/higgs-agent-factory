# Feedback filed in boson-ai/Boson-Feedback-Collection

Filed by Glib's approval, 2026-10-24, exactly as drafted below:
#40 (TTS `model`), #41 (TTS rate limit), #42 (transcript ahead of audio), #43 (avatar plugin fork), #44 (phone calls / SIP), #45 (IHBench client), comment on #18 (usage in audio mode, cached tokens), comment on #25 (avatar capacity).
https://github.com/boson-ai/Boson-Feedback-Collection/issues?q=author%3AHlibHav

Prepared 2026-10-24 per the repo's `skills/report-boson-issue/SKILL.md`. Each block is a separate issue (or a comment on an existing one). Times are EDT (UTC-4). No keys: the reproduction scripts use `***`. We did not keep request IDs; each draft says so.

Duplicate check (`gh issue list --state all`, 38 issues): our `usage` finding is covered by #18, and avatar `capacity_exhausted` by #25. For those two we add a comment with new evidence instead of a new issue. Not filed at all: the VAD turn split (still unverified on our side) and the tool-output follow-up (`response.create` after `function_call_output` is documented; that bug was ours).

---

## 1. New issue — `[TTS] /v1/audio/speech rejects a request without "model", which the API reference marks optional`

### Product
TTS

### Issue type
Bug / Docs

### Severity
Minor

### What happened?
Summary: A request that leaves out `model` fails with HTTP 400, while the API reference documents `model` as optional with default `higgs-tts-3`.
Expected: The request succeeds with the default model, or the reference marks `model` as required.
Actual: `400 invalid_request_error` with a pydantic `missing` error on `loc ('model',)`. The same request with `"model": "higgs-tts-3"` returns 200 `audio/pcm`.

### How to reproduce
```bash
# 400: missing model
curl -s -X POST https://api.boson.ai/v1/audio/speech \
  -H "Authorization: Bearer ***" -H 'Content-Type: application/json' \
  -d '{"input":"Hi.","voice":"chloe","response_format":"pcm","stream":true}'

# 200: same request with model
curl -s -X POST https://api.boson.ai/v1/audio/speech \
  -H "Authorization: Bearer ***" -H 'Content-Type: application/json' \
  -d '{"input":"Hi.","model":"higgs-tts-3","voice":"chloe","response_format":"pcm","stream":true}' -o out.pcm
```

### Details
SDK/API version: REST via curl and Python `httpx`
Model: higgs-tts-3
Endpoint/region: https://api.boson.ai/v1/audio/speech, client in Toronto, Canada
OS / language: macOS, Python 3.12
Request IDs + timestamps (with timezone): 2026-10-24 ~12:04 EDT (UTC-4); request IDs not kept
Logs:
```
{"error": {"message": "[{'type': 'missing', 'loc': ('model',), 'msg': 'Field required', ...}]", "type": "invalid_request_error", ...}}
```

### Evidence
The reference page lists `model` as optional with default `higgs-tts-3`: https://docs.boson.ai/api-reference/audio/create-a-speech. With `model` set, the stream returned 36,480 bytes of `audio/pcm` for "Hi.".

---

## 2. New issue — `[TTS] TTS rate limit is not documented; 429 rate_limit_exceeded at low request volume`

### Product
TTS

### Issue type
Bug / Docs

### Severity
Minor

### What happened?
Summary: `/v1/audio/speech` returned `429 rate_limit_exceeded` twice among about eight requests in two minutes from one key, and the docs give no TTS rate limit.
Expected: A documented TTS limit (requests per minute, concurrency), so a client can pace itself.
Actual:
```
{"error": {"message": "You have exceeded the rate limit. Please try again later.", "type": "rate_limit_error", "param": null, "code": "rate_limit_exceeded"}}
```
The 429s came between other responses: the next request, a few seconds later, returned 200 or a normal 400. Both 429s happened to be requests without `model` (see the separate issue about that field), so we can't rule out that the limit and the validation interact.

### How to reproduce
1. From one API key, send about eight short `/v1/audio/speech` requests within two minutes. We did this while debugging, with and without `model` and `voice`.
2. Some of them return the 429 above.
We did not capture the response headers of the 429, so we cannot say whether `Retry-After` was set.

### Details
Model: higgs-tts-3
Endpoint/region: https://api.boson.ai/v1/audio/speech, client in Toronto, Canada
OS / language: macOS, Python 3.12 (`httpx`), curl
Request IDs + timestamps (with timezone): 2026-10-24 between 12:02 and 12:05 EDT (UTC-4); request IDs not kept

### Evidence
https://docs.boson.ai/account-billing/usage-and-limits documents a Realtime concurrency limit but nothing for TTS.

---

## 3. New issue — `[Realtime] The assistant transcript arrives whole before the audio, so it never shows an interrupted answer`

### Product
Higgs Realtime

### Issue type
Docs / Behavior

### Severity
Minor

### What happened?
Summary: In audio mode, the full text of a response can arrive in the first `response.output_audio_transcript.delta`, before most of the audio. After a barge-in stops the audio, the transcript still holds the whole sentence.
Expected: Either the transcript tracks what was spoken, or the docs say that it doesn't, so clients don't treat it as "what the user heard". `response.output_audio_transcript.length` hints at the alignment, but the docs don't say the text runs ahead.
Actual: In one probe, `transcript.delta` with the full sentence arrived 0.279 s after `response.create`, and `response.output_audio.done` came at 0.631 s. In an interrupted turn, audio stopped 252 ms after the interruption began, but the transcript held the answer complete.

### How to reproduce
1. `session.update` with `output_modalities: ["audio"]`, `audio.input.turn_detection: null`, short instructions.
2. Add a user `input_text` item, send `response.create`.
3. Log `response.output_audio_transcript.delta` and `.done` against `response.output_audio.delta` and `.done` timestamps.

### Details
Model: higgs-realtime
Endpoint/region: wss://api.boson.ai/v1/realtime, client in Toronto, Canada
OS / language: macOS, Python 3.12 (`websockets`, and `pipecat-boson` 0.1.4)
Request IDs + timestamps (with timezone): probe 2026-10-24 ~12:15 EDT; interrupted turn ~12:30 EDT (UTC-4); session IDs not kept

### Evidence
Related, not a duplicate: #17 (stored item cut at an assumed playback point) and #30 (`conversation.item.truncate`). This one is about the transcript events.

---

## 4. New issue — `[Avatar] The LiveKit avatar plugin path depends on a commit in a personal fork; the PyPI release does not work`

### Product
Avatar

### Issue type
Docs / Packaging

### Severity
Minor

### What happened?
Summary: The realtime-sessions guide installs the avatar plugin from `git+https://github.com/warlockee/agents@808a4249850945f91609a9145e50ffea1c9802c4`, a personal fork, and warns that the PyPI `livekit-plugins-boson-avatar` 1.8.8 release does not work with this API.
Expected: A Boson-owned release we can pin, or a published timeline for one.
Actual: Teams that cannot install from personal forks have to rebuild the data-stream side themselves. We drove the avatar with `livekit-agents==1.8.9`'s `DataStreamAudioOutput` instead, without the plugin.

### How to reproduce
1. Open https://docs.boson.ai/models/higgs-avatar/realtime-sessions, LiveKit Agents section.
2. Compare the pinned install line with `pip install livekit-plugins-boson-avatar==1.8.8`.

### Details
Endpoint/region: docs as of 2026-10-24
OS / language: macOS, Python 3.12

---

## 5. New issue — `[Feedback] Phone calls: the solution cards describe calls, but Realtime has no SIP or WebRTC path`

### Product
Higgs Realtime

### Your idea or feedback
The solutions page describes call-centre use cases ("Automate outbound prospecting" for Health Insurance, "Classify incoming calls" for AI Receptionist). The migration guide says Realtime is WebSocket only: no SIP, no `/v1/realtime/calls`, and WebRTC "in progress". A builder reading the cards expects a documented path from a phone call to a Realtime session. Even a short note would help: a recommended telephony bridge (Twilio Media Streams, LiveKit SIP, …), the `audio/pcmu` 8 kHz settings to use, and what to expect on latency.

### What would it help you do?
Decide early whether a phone-facing agent is feasible on Higgs Realtime today, and which bridge to build, instead of finding out after building the voice side.

---

## 6. New issue — `[Other] IHBench's OpenAI realtime client cannot run against Higgs Realtime; a Higgs client is proposed in boson-ai/ihbench#2`

### Product
Other (IHBench, https://github.com/boson-ai/ihbench)

### Issue type
Compatibility

### Severity
Minor

### What happened?
Summary: Boson's interruption-recovery benchmark can't evaluate Boson's own Realtime API with its existing realtime client.
Expected: `scripts/run_inference_api.py --backend openai-realtime` with the Higgs base URL runs.
Actual: `ihbench/clients/openai_realtime_client.py` takes no `base_url`, and it would not work against Higgs anyway, because it:
- waits for `session.created` before sending `session.update` (Higgs sends nothing until the first update);
- sends user audio as `input_audio` content in `conversation.item.create` (Higgs skips it) and assistant history as `output_text` (Higgs expects `text`);
- waits for `conversation.item.done`, which Higgs never emits.

### How to reproduce
Read `ihbench/clients/openai_realtime_client.py` (session start, item creation, `conversation.item.done` counting) against https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration.

### Details
A Higgs Realtime client is proposed in boson-ai/ihbench#2 (draft): a new client, a config and one runner branch; 54 offline tests green on websockets 12.0 and 17.3; a live 10-sample smoke run with 0 failures; and a live check that replayed history keeps its order.

---

## 7. Comment on #18 (usage no longer null)

Adding two data points from 2026-10-24 (EDT):
- `usage` is also reported in **audio mode** on `higgs-realtime`. One gate turn reported 296 input, 272 cached and 20 output tokens; a six-scenario run reported 2,073 / 1,840 / 157.
- In our probe, `input_tokens` **included** `input_token_details.cached_tokens` rather than adding to it, so the billable non-cached count is `input_tokens - cached_tokens`. The docs don't state this either way; one sentence would settle it.

---

## 8. Comment on #25 (avatar 429 capacity_exhausted)

More detail from our side, 2026-10-24:
- `POST /v1/avatar/sessions` returned `429`, `code: capacity_exhausted`, message "Every realtime avatar slot is in use; try again later.", with a `Retry-After: 5` header.
- Every create was refused from 14:17 to 14:29 EDT (18:17–18:29 UTC), 12+ minutes. Creates had worked at 14:04–14:07 EDT.
- Nothing is created on a 429, so retrying is safe. We now wait up to 20 s for a slot and then show "avatar unavailable".
- `GET /v1/avatar/sessions` (list) returns 405, so a client can't check whether its own sessions are holding slots.
- It would help to know whether the pool is shared across all keys during the hackathon, and how many slots it has.
