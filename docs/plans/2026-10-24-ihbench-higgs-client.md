# Implementation Plan: IHBench client for Higgs Realtime
Status: ready
Spec: specs/2026-10-24-ihbench-higgs-client.md (SPEC-2026-10-24-ihbench-higgs-client)
Execution mode: single-agent — chosen by the user
Save as: docs/plans/2026-10-24-ihbench-higgs-client.md

## Open questions & recommendations
- gap — AC-22 / runner — default assumed: the key check runs in `HiggsRealtimeClient.__init__`, and when `api_key` is None the client reads env `BOSON_API_KEY`. A bad key then stops the run at `make_client` with one message, instead of 3 retries × 10 samples. — recommendation: confirm — blocking: no
- gap — AC-20 / handshake — no criterion covers a rejected handshake (bad key, DNS, HTTP 4xx), because the connection never opens. Default assumed: wrap it as a failed attempt, logged with the same prefix and naming only the exception class and HTTP status, never headers. That way AC-32 counts it. — recommendation: add one line to AC-20 or a new AC — blocking: no
- gap — AC-17 / AC-36 — `response.done` with a status other than `completed` or `cancelled`, or no status at all. Default assumed: fail the attempt like AC-36, naming the status. Partial text is never a success (NFR Reliability). — recommendation: confirm — blocking: no
- feasibility — AC-21 — the "controllable clock" is the constructor kwarg `attempt_timeout_s` (default `60.0`, not a YAML key, so AC-27 is untouched). One test pins the default at 60. A second test proves the behaviour with a 0.2 s bound. Nobody waits 60 s for real. — recommendation: confirm that this reading of the verify is acceptable — blocking: no
- better way — AC-9 — the client imports `_wav_to_pcm24k_b64` from `ihbench/clients/openai_realtime_client.py:26` instead of copying it. Resampling is then byte-identical to the OpenAI client (Goal: results comparable). The cost: a sibling module's private helper. The PR description offers to promote it to `base.py` if the maintainers prefer. — blocking: no
- gap — AC-34 — the replay plan (audio decoding plus chunking) is built **before** connecting. A zero-sample WAV therefore fails with zero connections. That satisfies "nothing sent for that turn" and spends no credits. — blocking: no
- contradiction (upstream, out of scope) — `ihbench/config.py:99` `ModelConfig.make_client` is a second backend dispatcher that nothing calls. It stays untouched (AC-26). The PR description mentions it. — blocking: no
- naming — the offline-test branch is `chore/higgs-realtime-client-tests`. Project and global branch types are `feat/fix/chore/docs`, so there is no `test/`. — blocking: no

## Acceptance criteria (from the spec, verbatim)
- AC-1 WHEN the client opens a session for a sample, the system shall send `session.update` as its first message, without waiting for any server event (F1). — proof: red-first unit
- AC-2 The system shall name the model `higgs-realtime` and put the sample's system message in `instructions` in the first `session.update` (F1, F20). — proof: red-first unit
- AC-3 The system shall request text-only output with `output_modalities` `["text"]` in the first `session.update` (F6). — proof: red-first unit
- AC-4 The system shall set turn detection to null at the session path F24 names, in the first `session.update` (F16, F24). Whether null really disables VAD for appended audio is proven live by AC-14. — proof: red-first unit
- AC-5 The system shall set the session's `max_output_tokens` to the run's `max_new_tokens` (F20). — proof: red-first unit
- AC-6 WHEN `session.created` arrives after the first `session.update`, the system shall start replaying the history without waiting for `session.updated` (F14). — proof: red-first unit
- AC-35 The system shall not send a temperature in any session or response event, leaving the server default (F20), as the OpenAI realtime client leaves its own. — proof: red-first unit
- AC-37 WHEN opening the connection, the system shall authenticate with the API key in the way F23 describes for server-side clients. — proof: red-first unit
- AC-7 The system shall never send audio inside `conversation.item.create` (F3). — proof: red-first unit
- AC-8 WHEN replaying a user turn that has a WAV, the system shall send its audio as one or more `input_audio_buffer.append` events of at most 1 MiB of base64 each, followed by exactly one `input_audio_buffer.commit` (F4, F16). — proof: red-first unit
- AC-9 The system shall send user audio as 24 kHz, 16-bit, mono PCM, whatever the source WAV's rate and channel count (F4). — proof: red-first unit
- AC-10 WHEN replaying a user turn that has no WAV, the system shall add it as a user item with `input_text` content holding the turn's text (F3). — proof: red-first unit
- AC-34 IF a user turn's WAV decodes to zero samples, THEN the system shall fail that attempt before sending anything for that turn, and log one line naming the sample's turn. — proof: red-first unit
- AC-11 WHEN replaying an assistant turn with non-empty text, the system shall add it as an assistant item whose content type is `text` (F3). — proof: red-first unit
- AC-12 IF an assistant turn's text is empty, THEN the system shall send nothing for that turn. — proof: red-first unit
- AC-13 WHILE replaying the history, the system shall send items in the sample's history order and shall not send the next item until `input_audio_buffer.committed` has arrived for the preceding user audio commit (F16). — proof: red-first unit
- AC-14 WHEN a live replay of a sample with at least two user audio turns completes, the system shall have placed each committed user audio item after the item replayed just before it, as shown by the `previous_item_id` of each `input_audio_buffer.committed` event (F16), and no response shall have started before `response.create` (F24). — proof: e2e
- AC-15 The system shall not wait for `conversation.item.done` at any point (F5). — proof: red-first unit
- AC-16 WHEN the last history item has been replayed, the system shall send exactly one `response.create` (F16). — proof: red-first unit
- AC-17 WHEN `response.done` with status `completed` arrives for that response, the system shall return the concatenated text of its `response.output_text.delta` events as the sample's response (F6, F17). — proof: red-first unit
- AC-36 IF `response.done` arrives with status `cancelled`, THEN the system shall fail that attempt and log one line for it, never returning the partial text (F17). — proof: red-first unit
- AC-18 IF the server sends an event type the client does not handle, THEN the system shall ignore it and continue the sample (F5). — proof: red-first unit
- AC-19 IF an `error` event arrives at any point in a sample, THEN the system shall fail that attempt with an error naming the error type, and log one line for the event. — proof: red-first unit
- AC-20 IF the connection closes before `response.done`, THEN the system shall fail that attempt with an error naming the close code, or the terminal event that preceded the close, and log one line for the failed attempt (F5, F8, F13, F21). — proof: red-first unit
- AC-21 IF `response.done` has not arrived within 60 s of the attempt opening its connection, THEN the system shall close the connection, fail that attempt, and log one line for the timeout. — proof: red-first unit
- AC-22 IF the API key is missing, empty, or still the unexpanded placeholder `${BOSON_API_KEY}`, THEN the system shall fail before opening any connection, with a message that names `BOSON_API_KEY`. — proof: red-first unit
- AC-23 The system shall never write the API key into a log line, an error message or a response row. — proof: red-first unit
- AC-38 The system shall behave as AC-1 to AC-37 require on every version of the WebSocket library that the `realtime` extra allows, from its declared minimum to the newest, including reporting the close code (AC-20). — proof: red-first unit
- AC-24 WHEN the inference runner is started with backend `higgs-realtime`, the system shall run samples through the Higgs client, using the run's model and API key. — proof: red-first unit
- AC-25 WHEN the inference runner is started with backend `openai-realtime`, the system shall build the existing OpenAI realtime client with the same arguments as before this change. — proof: red-first unit
- AC-26 The PR shall change exactly three files: a new Higgs client, a new `configs/higgs-realtime.yaml`, and the inference runner. In the runner, the only existing line that changes is the backend-choices line, which gains `higgs-realtime`, and the only other change is one added dispatch branch. The runner's module docstring stays as it is. — proof: e2e
- AC-27 The `configs/higgs-realtime.yaml` model config shall set backend `higgs-realtime`, model `higgs-realtime`, the API key from `${BOSON_API_KEY}`, `max_new_tokens` 4096 and `max_workers` 1. — proof: red-first unit
- AC-28 WHEN the runner runs with `configs/higgs-realtime.yaml`, `--max-workers 1`, `--limit 10` and `--output responses/higgs-realtime.jsonl`, the system shall write exactly 10 rows to that file. The subset is the runner's first 10 samples. — proof: e2e
- AC-29 WHEN the AC-28 smoke run completes, the system shall have written every row with the runner's keys `sample_id`, `conversation_id`, `interruption_type`, `turn_depth` and `response`. — proof: e2e
- AC-30 WHEN the AC-28 smoke run completes, the system shall have written a `response` that is non-empty after trimming whitespace, in every row. — proof: e2e
- AC-31 WHEN the AC-28 smoke run completes, the runner shall report 10 responses saved and 0 failures. — proof: e2e
- AC-32 WHEN the AC-28 smoke run completes, the run log shall contain zero failed-attempt lines (AC-19, AC-20, AC-21, AC-34, AC-36), including those from attempts the runner retried. — proof: e2e
- AC-33 The system shall never send a `system`-role conversation item (F3). — proof: red-first unit

## Traceability
All tests are in `tests/test_higgs_realtime_client.py` (fork, branch `chore/higgs-realtime-client-tests`) unless marked otherwise.

| AC | step | test | proof |
|---|---|---|---|
| AC-1 | 3 | `test_first_message_is_session_update` | red-first unit |
| AC-2 | 3 | `test_session_update_model_and_instructions` | red-first unit |
| AC-3 | 3 | `test_session_update_text_only` | red-first unit |
| AC-4 | 3 | `test_turn_detection_null_at_f24_path_only` | red-first unit |
| AC-5 | 3 | `test_max_output_tokens_from_max_new_tokens` | red-first unit |
| AC-6 | 4 | `test_replay_starts_after_session_created_only` | red-first unit |
| AC-35 | 3 | `test_no_temperature_sent` | red-first unit |
| AC-37 | 3 | `test_handshake_bearer_header_no_key_in_url` | red-first unit |
| AC-7 | 4 | `test_no_audio_in_item_create` | red-first unit |
| AC-8 | 4 | `test_long_wav_split_into_appends_then_one_commit` | red-first unit |
| AC-9 | 4 | `test_audio_resampled_to_24k_mono_pcm16` | red-first unit |
| AC-10 | 4 | `test_text_user_turn_is_input_text_item` | red-first unit |
| AC-34 | 4 | `test_zero_sample_wav_fails_before_sending` | red-first unit |
| AC-11 | 4 | `test_assistant_turn_is_text_item` | red-first unit |
| AC-12 | 4 | `test_empty_assistant_turn_sends_nothing` | red-first unit |
| AC-13 | 4 | `test_next_item_waits_for_committed` | red-first unit |
| AC-14 | 8 | `tests/live_replay_order.py` (live, main session) | e2e |
| AC-15 | 4 | `test_completes_without_item_done` | red-first unit |
| AC-16 | 4 | `test_one_response_create_after_last_item` | red-first unit |
| AC-17 | 5 | `test_returns_concatenated_deltas_on_completed` | red-first unit |
| AC-36 | 5 | `test_cancelled_response_fails` | red-first unit |
| AC-18 | 5 | `test_unknown_events_ignored` | red-first unit |
| AC-19 | 5 | `test_error_event_fails_attempt` | red-first unit |
| AC-20 | 5 | `test_close_fails_attempt_naming_cause` (parametrized: 4429, 3000, 1013, idle_timeout) | red-first unit |
| AC-21 | 5 | `test_attempt_timeout_closes_and_fails`, `test_default_attempt_timeout_is_60s` | red-first unit |
| AC-22 | 3 | `test_bad_key_fails_before_connect` (parametrized: unset, empty, placeholder) | red-first unit |
| AC-23 | 5 | `test_key_never_in_failure_output` | red-first unit |
| AC-38 | 3, 5, 7 | `test_headers_kwarg_by_version`, `test_connect_uses_kwarg_of_installed_version`, `test_close_fails_attempt_naming_cause[1013]`, run on both venvs | red-first unit |
| AC-24 | 6 | `test_runner_builds_higgs_client` | red-first unit |
| AC-25 | 6 | `test_runner_openai_realtime_unchanged` | red-first unit |
| AC-26 | 8 | main session: `git -C … diff --name-only` plus a read of the runner diff | e2e |
| AC-27 | 2 | `test_config_has_five_values` | red-first unit |
| AC-28 | 8 | live smoke (main session), line count | e2e |
| AC-29 | 8 | live smoke, keys per row | e2e |
| AC-30 | 8 | live smoke, non-empty responses | e2e |
| AC-31 | 8 | live smoke, final stderr line | e2e |
| AC-32 | 8 | live smoke, prefix count in stderr = 0 | e2e |
| AC-33 | 4 | `test_no_system_role_item` | red-first unit |

## Red-first
All in `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py`, branch `chore/higgs-realtime-client-tests`:
- AC-1 → `test_first_message_is_session_update`
- AC-2 → `test_session_update_model_and_instructions`
- AC-3 → `test_session_update_text_only`
- AC-4 → `test_turn_detection_null_at_f24_path_only`
- AC-5 → `test_max_output_tokens_from_max_new_tokens`
- AC-6 → `test_replay_starts_after_session_created_only`
- AC-7 → `test_no_audio_in_item_create`
- AC-8 → `test_long_wav_split_into_appends_then_one_commit`
- AC-9 → `test_audio_resampled_to_24k_mono_pcm16`
- AC-10 → `test_text_user_turn_is_input_text_item`
- AC-11 → `test_assistant_turn_is_text_item`
- AC-12 → `test_empty_assistant_turn_sends_nothing`
- AC-13 → `test_next_item_waits_for_committed`
- AC-15 → `test_completes_without_item_done`
- AC-16 → `test_one_response_create_after_last_item`
- AC-17 → `test_returns_concatenated_deltas_on_completed`
- AC-18 → `test_unknown_events_ignored`
- AC-19 → `test_error_event_fails_attempt`
- AC-20 → `test_close_fails_attempt_naming_cause`
- AC-21 → `test_attempt_timeout_closes_and_fails`, `test_default_attempt_timeout_is_60s`
- AC-22 → `test_bad_key_fails_before_connect`
- AC-23 → `test_key_never_in_failure_output`
- AC-24 → `test_runner_builds_higgs_client`
- AC-25 → `test_runner_openai_realtime_unchanged`
- AC-27 → `test_config_has_five_values`
- AC-33 → `test_no_system_role_item`
- AC-34 → `test_zero_sample_wav_fails_before_sending`
- AC-35 → `test_no_temperature_sent`
- AC-36 → `test_cancelled_response_fails`
- AC-37 → `test_handshake_bearer_header_no_key_in_url`
- AC-38 → `test_headers_kwarg_by_version`, `test_connect_uses_kwarg_of_installed_version`, plus the whole file green in both venvs (`.venv` with the newest websockets, `.venv-ws12` with `websockets==12.0`)

## Review focus
- Handshake rejected (HTTP 401, DNS) before any frame → pinned by `test_handshake_failure_is_logged_without_key` in step 5 (also under Open questions).
- `response.done` with status missing or neither `completed` nor `cancelled` → pinned by `test_unexpected_done_status_fails` in step 5 (also under Open questions).
- Normal server close (1000) arriving right after a completed `response.done` must not fail the attempt → pinned by `test_close_after_done_returns_text` in step 5.
- `error` event while waiting for `input_audio_buffer.committed` (for example a rejected commit) → pinned by `test_error_during_replay_fails` in step 5.
- Importing the runner script runs `load_dotenv(<fork>/.env)`, which may inject a real `BOSON_API_KEY` into tests → pinned by the `clean_env` fixture used in `test_bad_key_fails_before_connect`, step 1.

## Context read
- `STATUS.md:20` — the fork doesn't exist and needs Glib's confirmation → step 0.
- `CLAUDE.md:10-16` — Boson facts only from `docs/boson-protocol.md`. The plan cites F1, F3–F6, F13, F14, F16, F17, F20, F21, F23, F24.
- `CLAUDE.md:56-64` + `.claude/agent-guard.json` — the fork pytest command is in the guard. The AC-26 `git -C` diff is main-session only. `tests/test_scaffold.py:35-46` requires the guard to equal the `| none |` rows of the Check table, in order.
- `CLAUDE.md:82-87` — `vendor-ref/` is read-only and never imported. The implementer works only in `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs`.
- `docs/reuse-map.md:16-27` — decision: client + YAML + about six runner lines.
- `docs/boson-protocol.md` F23 — `Authorization: Bearer <key>` on the handshake to `wss://api.boson.ai/v1/realtime`. F24 — `session.audio.input.turn_detection`. Whether null disables VAD is UNVERIFIED until AC-14.
- `scripts/smoke.py:43-73` — the verified wire shape of `session.update` (model, output_modalities, instructions, max_output_tokens, audio.input.turn_detection). No `session.type`.
- `results/smoke-20261024T145225Z.jsonl:7` — the text delta field is `delta` on `response.output_text.delta`. F2's evidence shows `response.status` inside `response.done`.
- `vendor-ref/ihbench/scripts/run_inference_api.py:38-68,106,113-115,138-141,183` — dispatcher, choices line, CLI defaults that beat the YAML, final stderr line format.
- `vendor-ref/ihbench/scripts/run_inference_api.py:79-83` — a turn with a WAV reaches the client as `GenericMessage(type="audio", content=<path>)` with no text.
- `vendor-ref/ihbench/ihbench/clients/openai_realtime_client.py:26-43,58-82` — the shape to copy: the audio helper and per-message branching. `openai` is imported lazily.
- `vendor-ref/ihbench/ihbench/clients/base.py:17-46,49-67,98-102` — `is_audio_content`, `GenericMessage`, `GenerationConfig`, `APIClient`.
- `vendor-ref/ihbench/pyproject.toml:19-24` — the `realtime` extra is `scipy>=1.10`, `websockets>=12.0`. No pytest, ruff or test config upstream.
- `vendor-ref/ihbench/.gitignore` — `.venv/` is not ignored. The plan uses the fork's local `.git/info/exclude`, never a committed `.gitignore` change (that would be a 4th file).
- No `.claude/skills/`, `.claude/rules/` or `docs/architecture-decisions/` exist in this repo, and the fork declares no architecture rules.
- Main-session research (websockets changelog): `websockets.connect` is the legacy client in 12.x–13.x (`extra_headers`) and the new client from 14.0 (`additional_headers`). The close code is read from `e.rcvd.code`, and `rcvd` may be None. Latest is 17.3.

## Affected surfaces
- fork `ihbench-higgs` → `ihbench/clients` → adapter → `ihbench/clients/higgs_realtime_client.py` (new, PR)
- fork → `configs` → config → `configs/higgs-realtime.yaml` (new, PR)
- fork → `scripts` → composition root → `scripts/run_inference_api.py` (changed: line 106 and one `elif` after line 46, PR)
- fork → tests → `tests/test_higgs_realtime_client.py` (new, test branch only)
- fork → tests → `tests/live_replay_order.py` (new, test branch only, not collected by pytest)

## Constraints
- PR = exactly three files. In the runner, only the choices line changes, plus one added `elif` branch. The docstring (`run_inference_api.py:15`) stays untouched. — source: spec AC-26, `docs/reuse-map.md:23-25` — complies: code commits touch only those three paths, and test commits only `tests/`.
- No dependency change: `websockets>=12.0` stays as the floor. — source: spec AC-38, AC-26 — complies: a version branch in `_headers_kwarg`, and the suite runs on 12.0 and newest.
- Boson wire facts only from `docs/boson-protocol.md`, never from OpenAI Realtime. — source: `CLAUDE.md:10-13` — complies: every wire field in a step cites an F-id or the smoke evidence file.
- The client is an adapter. `websockets` is imported only there. The runner's `make_client` is the composition root, so the client reads no config file. The env fallback for the key is the only env read (default `architecture-boundaries` §3.3; no fork rule declared).
- Secrets: the key travels only in the F23 header. It is never placed in the URL, a log line, an exception message or repr. Failure messages are built only from event `type`, error `type`/`code`, close code, status or exception class name, never from raw payloads or headers. — source: spec AC-22, AC-23, AC-37; `engineering-paved-path:security` A09.
- Untrusted input: server events are parsed with `json.loads`. Unknown types are ignored. Model output is returned verbatim, uninterpreted. — source: spec "Untrusted inputs".
- Failure logs: logger `logging.getLogger(__name__)`, level WARNING, one line per failed attempt, every line starting with `higgs-realtime attempt failed:`. The runner configures no logging, so only WARNING and above reaches stderr through Python's last-resort handler (AC-32 greps that prefix).
- `vendor-ref/` is never edited or imported. — source: `CLAUDE.md:84-85`.
- Python 3.10 compatible (fork `requires-python >=3.10`): no `asyncio.timeout`. Use `asyncio.wait_for` and `asyncio.TimeoutError`.
- Agent PRs stay draft until Glib reviews them (global CLAUDE.md, 90/10).

## Skills for the implementer
- `ihbench/clients/*.py`, `scripts/run_inference_api.py`, `configs/*.yaml`, `tests/*` in the fork → none — project rules only (no `.claude/skills/` here, none in the fork). Before saying "done", follow `engineering-paved-path:verify-done` (named in `CLAUDE.md:66-67`): the command plus its quoted result line.

## Lanes
n/a — single-agent

## Steps

0. **[Needs Glib's explicit confirmation. Main session, not the implementer.]** Fork and environments.
   - Fork `boson-ai/ihbench` on GitHub and clone it to `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs`. Add remote `upstream` = `boson-ai/ihbench`, `git fetch upstream`.
   - Create `feat/higgs-realtime-client` and `chore/higgs-realtime-client-tests`, both from `upstream/main`.
   - Append `.venv/`, `.venv-ws12/`, `.pytest_cache/` to the fork's `.git/info/exclude` (local, never committed).
   - `uv venv --python 3.12 .venv` + `uv pip install --python .venv -e ".[realtime]" pytest` (newest websockets; record the version).
   - `uv venv --python 3.12 .venv-ws12` + `uv pip install --python .venv-ws12 -e ".[realtime]" pytest "websockets==12.0"`.
   - No `uv.lock` and no `pyproject.toml` edit in the fork.
   - verify: `git -C /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs branch --list` → both branches. `.venv/bin/python -c "import importlib.metadata as m; print(m.version('websockets'))"` → 17.x. The same in `.venv-ws12` → `12.0`.
   - The implementer starts at step 1. If the fork path, either branch or either venv is missing, it returns `blocked`.

1. tests — red-first suite, on `chore/higgs-realtime-client-tests`
   - files: `tests/test_higgs_realtime_client.py` (new)
   - layer: tests (outside the PR)
   - skills: none — project rules only
   - turns green: none (writes all red-first tests listed above)
   - test first: the whole Red-first list. Build these helpers in the same file:
     - `client_module` fixture: `importlib.import_module("ihbench.clients.higgs_realtime_client")` inside the fixture, so collection succeeds and each test fails on its own.
     - `FakeConnection`: async context manager with `send(str)` (records parsed dicts with `time.monotonic()`), `recv()` (awaits a queue; a queued exception is raised), `close()` / `__aexit__` (sets `closed=True`). Its scripted reactions decide, per client message type, which events to enqueue and after what delay.
     - `fake_connect` recorder: monkeypatches `websockets.connect`, records `(url, kwargs)` and the call count, returns a `FakeConnection`.
     - Close injection: real `websockets.exceptions.ConnectionClosedError(websockets.frames.Close(code, ""), None)` from the installed library.
     - `write_wav(path, seconds, rate, channels)` and `write_empty_wav(path)`, both through stdlib `wave`.
     - `clean_env` fixture: `monkeypatch.delenv("BOSON_API_KEY", raising=False)`, applied after the runner module import.
     - runner loader: `importlib.util.spec_from_file_location` on `<fork>/scripts/run_inference_api.py`.
   - Key assertions (what is not obvious from the AC verify):
     - AC-4: exactly one `turn_detection` key anywhere in the first update (recursive walk), at `session.audio.input`, value `None`.
     - AC-35: no `temperature` key in any client message (recursive walk), with `GenerationConfig(temperature=1.0)`.
     - AC-37: the recorded URL is exactly `wss://api.boson.ai/v1/realtime`, the key appears nowhere in the URL, and the headers are `{"Authorization": "Bearer <key>"}` under the kwarg `_headers_kwarg(<installed version>)`.
     - AC-38: `_headers_kwarg` maps `"12.0"` and `"13.1"` → `"extra_headers"`, and `"14.0"` and `"17.3"` → `"additional_headers"`.
     - AC-9: the bytes decoded from all appends total 96000 ± 4 (one stereo-source frame = one 24 kHz mono sample = 2 bytes; the tolerance allows ±1 frame per spec).
     - AC-13: the timestamp of the first client message after `commit` is ≥ the delivery time of the 200 ms-delayed `committed`.
     - AC-21: `attempt_timeout_s=0.2`, the fake never sends `response.done` → raises, `fake.closed is True`, exactly one caplog record with the prefix and containing `timeout`. Plus `HiggsRealtimeClient("higgs-realtime", api_key="k").attempt_timeout_s == 60.0`.
     - AC-23: sentinel key `sk-SENTINEL-123` is absent from `str(exc)`, `caplog.text` and `capsys` output across the AC-19, AC-20 and AC-21 paths.
     - AC-25: the test monkeypatches `ihbench.clients.openai_realtime_client.OpenAIRealtimeClient` with a recorder and asserts kwargs `== {"model_name": "gpt-realtime", "api_key": "k", "reasoning_effort": None}` (upstream `run_inference_api.py:46`).
     - "One logged line" everywhere = exactly one caplog record whose message starts with `higgs-realtime attempt failed:`.
   - interfaces: produces the test names in Red-first. Consumes nothing yet.
   - verify: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` → every test fails or errors (ModuleNotFoundError / AttributeError / AssertionError), 0 passed. Record that run, then commit: `test: add offline tests for Higgs realtime client`.

2. config — `configs/higgs-realtime.yaml` (same branch, code commit touching only this file)
   - files: `configs/higgs-realtime.yaml` (new)
   - layer: config
   - skills: none — project rules only
   - turns green: `test_config_has_five_values` (loads YAML, asserts the dict equals exactly `{backend: higgs-realtime, model: higgs-realtime, api_key: "${BOSON_API_KEY}", max_new_tokens: 4096, max_workers: 1}`, no other keys)
   - test first: none
   - interfaces: produces the config consumed by step 8
   - verify: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py -k config` → `1 passed`

3. client — module, constructor, connect, session start
   - files: `ihbench/clients/higgs_realtime_client.py` (new)
   - layer: adapter
   - skills: none — project rules only
   - turns green: `test_first_message_is_session_update`, `test_session_update_model_and_instructions`, `test_session_update_text_only`, `test_turn_detection_null_at_f24_path_only`, `test_max_output_tokens_from_max_new_tokens`, `test_no_temperature_sent`, `test_handshake_bearer_header_no_key_in_url`, `test_bad_key_fails_before_connect`, `test_headers_kwarg_by_version`, `test_connect_uses_kwarg_of_installed_version`, `test_default_attempt_timeout_is_60s`
   - test first: none (the red tests cover it)
   - interfaces: produces
     - `URL = "wss://api.boson.ai/v1/realtime"` (F1, F23)
     - `ATTEMPT_TIMEOUT_S = 60.0`
     - `LOG_PREFIX = "higgs-realtime attempt failed:"`
     - `MAX_APPEND_B64_CHARS = 1_048_576`
     - `class HiggsRealtimeError(RuntimeError)`
     - `def _headers_kwarg(ws_version: str) -> str`: major ≥ 14 → `"additional_headers"`, else `"extra_headers"`. The installed version comes from `importlib.metadata.version("websockets")`.
     - `class HiggsRealtimeClient(APIClient)` with `__init__(self, model_name: str, api_key: str | None = None, attempt_timeout_s: float = ATTEMPT_TIMEOUT_S, **kwargs: Any)`. It falls back to env `BOSON_API_KEY` when `api_key` is None, and raises `ValueError` naming `BOSON_API_KEY` when the key is empty, whitespace or `"${BOSON_API_KEY}"`. The message never includes the value.
     - `def _session_update(self, system_message: str, config: GenerationConfig) -> dict` returns `{"type": "session.update", "session": {"model": self.model_name, "output_modalities": ["text"], "instructions": system_message, "max_output_tokens": config.max_new_tokens, "audio": {"input": {"turn_detection": None}}}}` (F1, F6, F20, F24).
     - `def generate(self, system_message, messages, config=None) -> str` → `asyncio.run(self._generate_async(...))`.
     - The connection opens through `websockets.connect(URL, **{_headers_kwarg(v): {"Authorization": f"Bearer {key}"}})`, called as a module attribute so tests can patch it. `session.update` is sent immediately after connect (AC-1).
   - verify: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py -k "session_update or turn_detection or max_output or temperature or handshake or bad_key or headers_kwarg or connect_uses or default_attempt"` → all selected pass

4. client — replay plan and replay
   - files: `ihbench/clients/higgs_realtime_client.py` (changed)
   - layer: adapter
   - skills: none — project rules only
   - turns green: `test_replay_starts_after_session_created_only`, `test_no_audio_in_item_create`, `test_long_wav_split_into_appends_then_one_commit`, `test_audio_resampled_to_24k_mono_pcm16`, `test_text_user_turn_is_input_text_item`, `test_zero_sample_wav_fails_before_sending`, `test_assistant_turn_is_text_item`, `test_empty_assistant_turn_sends_nothing`, `test_next_item_waits_for_committed`, `test_completes_without_item_done`, `test_one_response_create_after_last_item`, `test_no_system_role_item`
   - test first: `test_chunk_b64_boundaries`: `_chunk_b64("A"*(2*1_048_576+8))` gives 3 chunks, each ≤ 1,048,576 characters with length a multiple of 4, and `"".join(chunks)` equals the input.
   - interfaces:
     - consumes `_wav_to_pcm24k_b64` from `ihbench.clients.openai_realtime_client` (F4 format), `is_audio_content` from `ihbench.clients.base`, and step 3's names.
     - produces `def _chunk_b64(b64: str, limit: int = MAX_APPEND_B64_CHARS) -> list[str]`.
     - produces `def _build_replay(self, messages: list[GenericMessage]) -> list[tuple[str, Any]]`. Steps are `("audio", list[str])` or `("item", dict)`. It runs **before** connecting.
     - Branching mirrors `openai_realtime_client.py:61-81`:
       - audio + `is_audio_content` → `("audio", chunks)`, or `HiggsRealtimeError(f"{LOG_PREFIX} user turn {i} audio has zero samples")` when the PCM is empty (AC-34);
       - user text → item `{"type": "message", "role": "user", "content": [{"type": "input_text", "text": ...}]}` (F3);
       - assistant non-empty → `{"type": "message", "role": "assistant", "content": [{"type": "text", "text": ...}]}` (F3);
       - assistant empty → nothing.
     - The system message never becomes an item (AC-33, F3).
     - Replay order: send `session.update` → wait for `session.created`, never `session.updated` (F14). Then each step in order:
       - audio: appends, then one `input_audio_buffer.commit`, then wait for `input_audio_buffer.committed` (F16);
       - item: `conversation.item.create`, no wait (F5).
     - Then exactly one `{"type": "response.create"}`.
     - produces `async def _wait_for(self, ws, event_type: str, state: dict) -> dict`, the single event reader that steps 4 and 5 share:
       - ignores unknown types;
       - raises on `error`;
       - remembers `session.idle_timeout` / `session.max_duration_reached` in `state["terminal"]`;
       - maps `ConnectionClosed` to `HiggsRealtimeError`.
       - Its error branches are completed in step 5.
   - verify: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py -k "replay or audio or wav or text_user or assistant or committed or item_done or response_create or system_role or chunk"` → all selected pass

5. client — response, failures, timeout, logging
   - files: `ihbench/clients/higgs_realtime_client.py` (changed)
   - layer: adapter
   - skills: none — project rules only
   - turns green: `test_returns_concatenated_deltas_on_completed`, `test_cancelled_response_fails`, `test_unknown_events_ignored`, `test_error_event_fails_attempt`, `test_close_fails_attempt_naming_cause`, `test_attempt_timeout_closes_and_fails`, `test_key_never_in_failure_output`
   - test first:
     - `test_handshake_failure_is_logged_without_key`: patched connect raises `OSError("boom")` → `HiggsRealtimeError`, one prefixed record naming `OSError`, sentinel absent.
     - `test_unexpected_done_status_fails`: `response.done` with `status: "failed"` → raises, one record naming `failed`.
     - `test_close_after_done_returns_text`: completed `response.done`, then 1000 close → returns the text.
     - `test_error_during_replay_fails`: `error` instead of `committed` → raises naming the error type.
   - interfaces:
     - consumes step 4's `_wait_for` and `state`.
     - Text = join of `event["delta"]` for `response.output_text.delta`. On `response.done`, read `event["response"]["status"]`: `completed` → return the text; anything else → `HiggsRealtimeError(f"{LOG_PREFIX} response {status}")` (AC-36, F17).
     - `error` → `HiggsRealtimeError(f"{LOG_PREFIX} error event {error.type}")`, adding `error.code` when present, never `message` (AC-19, F13).
     - `ConnectionClosed e` → name `e.rcvd.code` if `e.rcvd` else "no close frame", or `state["terminal"]` when set (AC-20).
     - The whole attempt (connect through `response.done`) runs under `asyncio.wait_for(..., self.attempt_timeout_s)`. On `asyncio.TimeoutError` the `async with` exit closes the connection, and the client raises `HiggsRealtimeError(f"{LOG_PREFIX} no response.done within {self.attempt_timeout_s:g}s (timeout)")` (AC-21).
     - Other exceptions from connect are wrapped as `HiggsRealtimeError(f"{LOG_PREFIX} connection failed: {type(e).__name__}")`.
     - Exactly one place logs: `_generate_async` catches `HiggsRealtimeError`, calls `_log.warning("%s", err)`, and re-raises. The AC-34 failure goes through the same place.
   - verify: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py -k "deltas or cancelled or unknown or error or close or timeout or key_never or handshake or done_status"` → all selected pass

6. runner — backend choice and dispatch branch
   - files: `scripts/run_inference_api.py` (changed)
   - layer: composition root
   - skills: none — project rules only
   - turns green: `test_runner_builds_higgs_client`, `test_runner_openai_realtime_unchanged`
   - test first: none
   - interfaces:
     - consumes `HiggsRealtimeClient(model_name, api_key)`.
     - Line 106: the `choices` list gains `"higgs-realtime"` right after `"openai-realtime"`. That is the only modified existing line.
     - Insert after line 46: `elif args.backend == "higgs-realtime":`, a lazy `from ihbench.clients.higgs_realtime_client import HiggsRealtimeClient`, a blank line, `return HiggsRealtimeClient(model_name=args.model, api_key=args.api_key)`. Same shape as lines 43-46.
     - The docstring (line 15) is not touched.
   - verify: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py -k runner` → `2 passed`

7. tests + branches — live AC-14 harness, both library versions, carry code to the PR branch
   - files: `tests/live_replay_order.py` (new, test branch only; the implementer writes it and **never runs it**: it needs the network and spends credits)
   - layer: tests (outside the PR)
   - skills: none — project rules only
   - turns green: AC-38 (whole file on `.venv-ws12`)
   - test first: none
   - interfaces:
     - The harness loads samples through `load_eval_samples_from_hf("bosonai/ihbench", ".ihbench_audio_cache")` and picks the first sample whose history has ≥ 2 user turns with an existing WAV.
     - It wraps `websockets.connect` in a recording proxy and runs `HiggsRealtimeClient("higgs-realtime", api_key=None).generate(...)` once.
     - It writes every sent and received message to `results/ac14-<utc>.jsonl`. Audio payloads are replaced by their length. Headers are never recorded.
     - It prints three lines:
       - each `committed.previous_item_id` against the id of the item replayed just before it;
       - whether any `response.*` event came before the client's `response.create`;
       - the event types received after each `conversation.item.create`.
   - Branch work, in order:
     - (a) commit steps 2–6 on `chore/higgs-realtime-client-tests` as code commits touching only the three PR paths, and step 7's harness in a `test:` commit;
     - (b) `git switch feat/higgs-realtime-client`, then `git cherry-pick` the code commits only;
     - (c) `git switch chore/higgs-realtime-client-tests`, then `git rebase feat/higgs-realtime-client` (git drops the already-applied code commits);
     - (d) `git log --oneline feat/higgs-realtime-client..chore/higgs-realtime-client-tests` lists only `test:` commits.
   - verify:
     - `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` → all passed, 0 failed;
     - `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv-ws12/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` → all passed, 0 failed;
     - `git diff --name-only feat/higgs-realtime-client chore/higgs-realtime-client-tests` → only `tests/` paths.

8. **[Main session, live, spends Boson credits, never in the guard.]** Footprint, AC-14, smoke, PR
   - AC-26: `git -C /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs diff --name-only upstream/main...feat/higgs-realtime-client` → exactly `configs/higgs-realtime.yaml`, `ihbench/clients/higgs_realtime_client.py`, `scripts/run_inference_api.py`. Then read `git -C … diff upstream/main...feat/higgs-realtime-client -- scripts/run_inference_api.py` → one `-`/`+` pair on the choices line, one added `elif` block, and nothing else.
   - AC-14 first (one sample, cheap). With cwd `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs` on the test branch, `BOSON_API_KEY` in env or the fork's `.env`: `.venv/bin/python tests/live_replay_order.py` → every audio `previous_item_id` matches, "no response before response.create", and the text-item acks recorded. **If it fails, stop**: this is the spec's implementer blocker (Q1 option b). Go back to spec-creator. No silent fallback.
   - Smoke (AC-28…32), on `feat/higgs-realtime-client`, same cwd: `.venv/bin/python scripts/run_inference_api.py --config configs/higgs-realtime.yaml --max-workers 1 --limit 10 --output responses/higgs-realtime.jsonl 2> responses/higgs-realtime.stderr.log`. Then:
     - AC-28: line count of `responses/higgs-realtime.jsonl` = 10;
     - AC-29/30: each row has the five keys and `response.strip()` is non-empty;
     - AC-31: the last line of the stderr log reads `Done. 10 responses saved to responses/higgs-realtime.jsonl, 0 failures.`;
     - AC-32: count of `higgs-realtime attempt failed:` in the stderr log = 0.
   - Afterwards, record F24 (VAD off with null) and the text-item ack behaviour as VERIFIED-RUN in `docs/boson-protocol.md` with the `results/ac14-*.jsonl` evidence. Any RQ number or cost figure needs a `docs/CLAIMS.md` row.
   - PR: open as **draft** to `boson-ai/ihbench` only after Glib's OK. The description covers:
     - F1/F3/F5 as the reason (FRICTION row);
     - the three-file footprint;
     - YAML `max_workers` is inert (the runner CLI default wins), so use `--max-workers 1`;
     - `temperature` is not sent;
     - `ModelConfig.make_client` is an unused second dispatcher, left untouched;
     - the private-helper import offer;
     - the generic API-backend registry proposal;
     - model output is a prompt-injection path into the RQ judge;
     - the offline tests offered from `chore/higgs-realtime-client-tests`, green on websockets 12.0 and newest.

## Contracts & data
- Runner backend value `higgs-realtime`, added to the choices at `run_inference_api.py:106`.
- `configs/higgs-realtime.yaml`: exactly the five keys of AC-27. No `temperature`, no new keys.
- Client contract: `generate(system_message, messages, config) -> str`, or raises `HiggsRealtimeError` (`ValueError` at construction for a bad key). Only `config.max_new_tokens` is used.
- Log contract: one WARNING line per failed attempt, prefix `higgs-realtime attempt failed:`. AC-32 depends on it.
- Responses file: unchanged runner format.
- No schema, migration or message catalog.

## Checks for the implementer
- fork `ihbench-higgs` (single-agent; the fork declares no typecheck and no lint, since upstream has no ruff/mypy config, so none is run):
  - `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` (newest websockets)
  - `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv-ws12/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` (declared minimum, AC-38)

## Checks for reviewers          (plan-verifier first, then the rest in parallel)
- sdd-engineering:plan-verifier:
  - AC-1…AC-13, AC-15…AC-25, AC-27, AC-33…AC-38 through the offline suite on `.venv`. The `.venv-ws12` run counts once its command is in the guard; until then it is main-session evidence for AC-38.
  - AC-14 and AC-26 are main-session evidence.
  - AC-28…AC-32 come from the main session's live smoke logs.
  - No integration suite exists.
- architecture-review:architecture-reviewer: no boundary check is declared in the fork. Read the three PR files against: client = adapter (only place `websockets` is imported, no config-file reads); runner = composition root (one branch, lazy import like its neighbours); no edits outside the three files.
- security: `/security-review` of the `feat/higgs-realtime-client` diff in the fork. Focus: the key appears only in the handshake header (AC-23, AC-37), failure messages carry no payloads, model output is passed through untouched.
- main session: `/code-review` of the same diff, the AC-26 git diff, the live AC-14 harness, the live smoke AC-28…AC-32, and the draft PR after Glib's OK.

## Commands for the read-only agents
Each must be listed in `.claude/agent-guard.json` → `checkCommands`, or the guard hook denies it and the check is reported unverifiable. One plain command per line, no pipes, `&&`, `;` or redirects.
- `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` — run by plan-verifier (already in the guard and in the `CLAUDE.md` Check table).
- `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv-ws12/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` — run by plan-verifier for AC-38. **Not yet in the guard.** The main session should add it to `checkCommands` **and** as a `| none |` row in the `CLAUDE.md` Check table, in the same order, or `tests/test_scaffold.py::test_agent_guard_matches_offline_checks_in_claude_md` goes red. Until then AC-38's minimum-version run is main-session evidence.
- Never in the guard:
  - the AC-26 `git -C …` diff (the guard denies `git` options before the subcommand);
  - `tests/live_replay_order.py`;
  - the smoke `scripts/run_inference_api.py` command;
  - anything that downloads the HF dataset or spends Boson credits.

## Out of scope
- Writing or changing the spec (spec-creator), architecture review (architecture-review:architecture-reviewer), acceptance verification (plan-verifier), security review and end-to-end runs (main session and security reviewer).
- Fixing the runner's YAML-override precedence, `ModelConfig.make_client`, the README's "Adding a model" section, the judge or the dataset.
- Audio output, voices, tools, server VAD, a configurable endpoint, cost accounting, `max_workers` > 1.
- Any edit to `vendor-ref/` or to this repo's code. This repo only gets the plan, the evidence and the protocol/claims rows from step 8.

## Risks
- **F24 null may not disable VAD** for appended audio (UNVERIFIED). Then responses start mid-replay and AC-19/AC-32 go red live. AC-14 runs first to catch this cheaply, and failure means going back to spec-creator (Q1 option b).
- **websockets 12.0 on Python 3.12.** The main session's research covered the API, not install compatibility. If `uv pip install "websockets==12.0"` fails on 3.12, build `.venv-ws12` with `--python 3.11` and note it. The floor stays as is.
- **`websockets.frames.Close` / `ConnectionClosedError(rcvd, sent)` constructor in the tests.** The research documents `rcvd` from 12.0. If constructing it differs on 12.0, the fake builds the exception the way that version documents. Don't change the client to fit the test; if the client's reading of `e.rcvd.code` is wrong on 12.0, flag it.
- **First smoke run downloads the HF dataset and audio cache** (`.ihbench_audio_cache/`, size not known here). Network and disk only, no Boson cost, but it can be slow.
- **The private helper `_wav_to_pcm24k_b64`** can be renamed upstream. It is pinned by the AC-9 test, and the PR description offers to promote it.
- **Credits.** The live AC-14 run and the 10-sample smoke spend Boson credits (F12 rates). Show no cost figure without a `docs/CLAIMS.md` row. Runner retries (3 × 60 s per sample) bound the worst case in time, not in tokens: output is capped by `max_output_tokens` (AC-5).
