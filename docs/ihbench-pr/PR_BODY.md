<!-- PR title: Add Higgs Realtime client (higgs-realtime backend) -->

Adds the public client for running IHBench against Boson's Higgs Realtime API, the benchmark Boson already reports on.

## What it adds

Three files, no new dependencies, existing clients untouched:

- `ihbench/clients/higgs_realtime_client.py` (new): `HiggsRealtimeClient`, text output over the Higgs Realtime WebSocket (`wss://api.boson.ai/v1/realtime`).
- `configs/higgs-realtime.yaml` (new): `backend: higgs-realtime`, `model: higgs-realtime`, key from `${BOSON_API_KEY}`.
- `scripts/run_inference_api.py`: about six lines. `higgs-realtime` joins the `--backend` choices, and `make_client` gets one `elif` branch that builds the new client.

## Why the OpenAI realtime client can't be reused

`openai_realtime_client.py` stalls or loses history against Higgs, for three reasons ([migration notes](https://docs.boson.ai/models/higgs-realtime/migrate-an-existing-integration)):

1. **Higgs speaks second.** The server sends nothing until the client sends `session.update`, and `session.created` is the reply to that first update. The OpenAI client waits for `session.created` before it sends anything, so it waits forever.
2. **History items are text only.** `conversation.item.create` skips `input_audio` content, and assistant messages must use `text` (`output_text` is not recognised). The OpenAI client replays user audio as `input_audio` items and assistant turns as `output_text`, so Higgs would skip the user audio and not recognise the assistant turns.
3. **`conversation.item.done` is never sent.** The OpenAI client waits on it for every replayed item.

What the new client does instead: it sends `session.update` first (`model`, `instructions`, `output_modalities: ["text"]`, `max_output_tokens` from `max_new_tokens`, `audio.input.turn_detection: null`) and waits for `session.created`. It replays user audio as 24 kHz PCM16 mono (reusing the existing `_wav_to_pcm24k_b64`) through `input_audio_buffer.append` in chunks of at most 1 MiB of base64, then one `commit`, and waits for `input_audio_buffer.committed`. Assistant turns go in as `text` items. One `response.create` follows, and the text deltas up to `response.done` are the answer. An `error` event, a close before `response.done` (close code named), a non-`completed` response, a 60 s timeout or a zero-sample WAV each fail the attempt with one `WARNING` line. The API key never appears in logs or error messages. It works on every `websockets` the `realtime` extra allows: 12.x–13.x take `extra_headers`, 14+ take `additional_headers`.

## How to reproduce

```bash
pip install -e ".[realtime]"          # or ".[api]"
export BOSON_API_KEY=...              # your Boson key

python scripts/run_inference_api.py \
    --config configs/higgs-realtime.yaml \
    --max-workers 1 --limit 10 \
    --output responses/higgs-realtime.jsonl
```

`--max-workers 1` has to be on the command line (see the notes below). `--limit 10` takes the runner's first 10 samples in dataset order, which may come from only one or two conversations: it proves the protocol path, not coverage of every interruption type.

## Results measured

- Smoke run, the command above: `Done. 10 responses saved to responses/higgs-realtime.jsonl, 0 failures.`
- Replay order, checked live: each `input_audio_buffer.committed.previous_item_id` points at the item sent just before it, and no response starts before `response.create`.
- Offline tests with a fake WebSocket: 50 passed on websockets 17.3 and 50 passed on websockets 12.0 (the `realtime` extra's floor).
- Footprint: `git diff --name-only upstream/main...` lists exactly the three files above.

## What is not included

- **The tests.** The 50 offline tests live on [`chore/higgs-realtime-client-tests`](https://github.com/HlibHav/ihbench/tree/chore/higgs-realtime-client-tests) to keep this PR small, since the repo has no `tests/` folder yet. Happy to add them here if you want one.
- **Judge numbers.** This PR claims no IHBench TF or RQ score for Higgs Realtime. Only inference was run, on 10 samples; `run_evaluate.py` was not run on the output.
- **Audio output.** The client asks for text output only, which is what the judges read.

## Known limitations

- On `websockets` 12.x–13.x (legacy client, `extra_headers`), a cross-host HTTP redirect during the handshake would resend the `Authorization` header to the new host; 14+ strips it. `api.boson.ai` does not redirect today. Prefer `websockets>=14` when you can.

## Notes for reviewers

- `max_workers` in YAML has no effect: a YAML value is applied only when the CLI arg is `None`, and `--max-workers` defaults to 8. That is why the command passes `--max-workers 1`. The Realtime concurrency limit is not documented, and going over it closes the socket with code 1013. This affects every config; I can send a separate fix.
- `temperature` is not sent, so the server default applies. The OpenAI realtime client ignores it too.
- The client imports the private `_wav_to_pcm24k_b64` from `openai_realtime_client.py` so resampling stays byte-identical. Happy to move it to `base.py`.
- `ihbench/config.py` `ModelConfig.make_client` looks like an unused second dispatcher, so I left it alone.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
