# Spec: IHBench client for Higgs Realtime
Spec ID: SPEC-2026-10-24-ihbench-higgs-client
Status: implemented
Tier: Full SDD — scorecard 4/6 (raised by spec-creator from the main session's 3/6, Lightweight: Q2 became "yes" because a sample's multi-turn history can be replayed two ways)
Supersedes: none
Packages: the fork `../ihbench-higgs` of `boson-ai/ihbench`, branch `feat/higgs-realtime-client`, PR to `boson-ai/ihbench`. The spec lives in this repo. The code lives in the fork.
Design sources: user text, 2026-10-24: the brief for P0 (`docs/BRIEF.md`), the reuse map (`docs/reuse-map.md`, section "ihbench: how our client fits"), the friction log (`docs/FRICTION.md`), and Glib's answers of 2026-10-24 on runner edits, history replay, timeout, token cap, smoke size, concurrency, where the tests live, worker count, empty audio, cancelled responses and protocol facts. Boson facts are cited by id from `docs/boson-protocol.md`.

## Problem and user

IHBench is Boson's interruption-recovery benchmark. It cannot run against Boson's own Higgs Realtime API. Its OpenAI realtime client waits for an event Higgs does not send first (F1), sends user audio in a form Higgs skips and names assistant text in a form Higgs does not recognise (F3), and waits for an event Higgs never emits (F5). The user is two people: Boson's IHBench maintainers, who get a small reviewable PR that lets their benchmark score their own model, and us, because P1's Eval Card reads the responses file this client produces.

## Outcome and metrics

- Outcome: an IHBench run against Higgs Realtime produces one response row per sample, and the PR is open against `boson-ai/ihbench`.
- Metric 1: on the smoke subset (10 samples), rows written = 10, runner failures = 0, client-logged failed attempts = 0 (AC-28 to AC-32).
- Metric 2: the PR changes three files: one new client, one new model config, and the runner's backend registration (AC-26).
- RQ scores computed from these responses are not a metric of this spec. Any RQ number that reaches a stage, the PR or the friction log needs a row in `docs/CLAIMS.md`.

## Goals / Non-goals

Goals
- Run IHBench samples against Higgs Realtime. Each user turn is replayed as audio and each assistant turn as text, in history order, so the setup matches the existing OpenAI realtime client and RQ results stay comparable with the paper (Glib, Q1).
- Respect the Higgs protocol as documented: F1, F3, F4, F5, F6, F14, F16, F17, F20, F23, F24, plus the close and error behaviour in F13 and F21.
- Fail a sample attempt loudly on any protocol error, close, cancellation, timeout or unusable audio, so the runner's retry and failure accounting see it.
- Keep the PR small: a new client, a new model config, and the minimum runner edit (one backend choice, one dispatch branch). Glib's decision of 2026-10-24 is recorded in `docs/reuse-map.md`.
- Keep the existing OpenAI realtime client's behaviour unchanged.

Non-goals
- Changing the benchmark, the dataset, the judge or the evaluation script.
- Making the YAML `max_workers` key take effect. The runner's command-line default wins over it, so the config value is documentation only. The smoke command passes the worker count explicitly (AC-28), and the PR description names the dead key (Glib, 2026-10-24). The same holds for `temperature`, which the client does not send anyway (AC-35).
- A generic registry for API backends. It is proposed in the PR description only (FRICTION.md row "two files, zero runner edits").
- Audio output, voices (F7), tools (F10) and server VAD. The client is text-out and drives turns manually.
- A configurable endpoint. The client connects to the endpoint in F1.
- Cost accounting per sample. Docs and wire disagree on whether `response.done` carries usage (F2), and the benchmark's row format has no field for it.
- Offline tests inside the PR. They live on a separate branch of the fork, and the PR description offers them to the maintainers (Glib, Q6).
- Raising `max_workers` above 1 before the concurrency limit (F21) is known.
- Raising the minimum version of the WebSocket library that the `realtime` extra declares. The client works across the whole allowed range instead (AC-38).

## User stories

- As an IHBench maintainer, I run the documented inference command with the Higgs model config and get a responses file I can judge like any other model's.
- As a reviewer of the PR, I see three changed files, and the runner change is one backend choice plus one dispatch branch.
- As the P1 Eval Card, I read a responses file whose rows all came from runs with no protocol error.

## Acceptance criteria (EARS)

Session start
- AC-1 WHEN the client opens a session for a sample, the system shall send `session.update` as its first message, without waiting for any server event (F1). — proof: red-first unit — verify: a fake server that stays silent until it receives a message; run one sample; expect the first client message to be `session.update`.
- AC-2 The system shall name the model `higgs-realtime` and put the sample's system message in `instructions` in the first `session.update` (F1, F20). — proof: red-first unit — verify: capture the first `session.update` for a sample with system message "S"; expect model `higgs-realtime` and instructions "S".
- AC-3 The system shall request text-only output with `output_modalities` `["text"]` in the first `session.update` (F6). — proof: red-first unit — verify: capture the first `session.update`; expect exactly `["text"]`.
- AC-4 The system shall set turn detection to null at the session path F24 names, in the first `session.update` (F16, F24). Whether null really disables VAD for appended audio is proven live by AC-14. — proof: red-first unit — verify: capture the first `session.update`; expect turn detection present and null at the F24 path, and absent from any other path.
- AC-5 The system shall set the session's `max_output_tokens` to the run's `max_new_tokens` (F20). — proof: red-first unit — verify: run with `max_new_tokens` 4096; expect `max_output_tokens` 4096 in the first `session.update`.
- AC-6 WHEN `session.created` arrives after the first `session.update`, the system shall start replaying the history without waiting for `session.updated` (F14). — proof: red-first unit — verify: a fake server that answers the first update with `session.created` only; expect history items to follow.
- AC-35 The system shall not send a temperature in any session or response event, leaving the server default (F20), as the OpenAI realtime client leaves its own. — proof: red-first unit — verify: run with the runner's temperature 1.0; expect no temperature field in any client message.
- AC-37 WHEN opening the connection, the system shall authenticate with the API key in the way F23 describes for server-side clients. — proof: red-first unit — verify: a fake server that records the handshake; expect the F23 authorization header carrying the given key, and no key in the URL.

History replay
- AC-7 The system shall never send audio inside `conversation.item.create` (F3). — proof: red-first unit — verify: replay a history with three audio user turns; expect zero `conversation.item.create` events carrying audio content.
- AC-8 WHEN replaying a user turn that has a WAV, the system shall send its audio as one or more `input_audio_buffer.append` events of at most 1 MiB of base64 each, followed by exactly one `input_audio_buffer.commit` (F4, F16). — proof: red-first unit — verify: a 40 s WAV turn; expect at least two appends, each payload ≤ 1,048,576 base64 characters, then one commit.
- AC-9 The system shall send user audio as 24 kHz, 16-bit, mono PCM, whatever the source WAV's rate and channel count (F4). — proof: red-first unit — verify: a 2.0 s, 16 kHz stereo WAV; expect the decoded appended bytes to total 2.0 × 24000 × 2 bytes, within one frame.
- AC-10 WHEN replaying a user turn that has no WAV, the system shall add it as a user item with `input_text` content holding the turn's text (F3). — proof: red-first unit — verify: a history whose first user turn comes as a text message; expect one user `input_text` item with that text and no append for it.
- AC-34 IF a user turn's WAV decodes to zero samples, THEN the system shall fail that attempt before sending anything for that turn, and log one line naming the sample's turn. — proof: red-first unit — verify: a history whose second user turn is a valid WAV header with no frames; expect the attempt to raise, no append or commit for that turn, and one logged line.
- AC-11 WHEN replaying an assistant turn with non-empty text, the system shall add it as an assistant item whose content type is `text` (F3). — proof: red-first unit — verify: an assistant turn "Sure, the"; expect one assistant item with content type `text` and that text, and no `output_text` anywhere.
- AC-12 IF an assistant turn's text is empty, THEN the system shall send nothing for that turn. — proof: red-first unit — verify: an assistant turn with empty text; expect no item for it.
- AC-13 WHILE replaying the history, the system shall send items in the sample's history order and shall not send the next item until `input_audio_buffer.committed` has arrived for the preceding user audio commit (F16). — proof: red-first unit — verify: a fake server that delays `committed` by 200 ms; expect the next history event only after it.
- AC-14 WHEN a live replay of a sample with at least two user audio turns completes, the system shall have placed each committed user audio item after the item replayed just before it, as shown by the `previous_item_id` of each `input_audio_buffer.committed` event (F16), and no response shall have started before `response.create` (F24). — proof: e2e — verify: live run of one multi-turn sample with the full event log kept; expect each audio item's `previous_item_id` to point at the preceding replayed item, no response event before `response.create`, and the log to record whatever acknowledgement the server sends for text items.
- AC-15 The system shall not wait for `conversation.item.done` at any point (F5). — proof: red-first unit — verify: a fake server that never sends `conversation.item.done`; expect the sample to finish with a response.

Response
- AC-16 WHEN the last history item has been replayed, the system shall send exactly one `response.create` (F16). — proof: red-first unit — verify: replay a 5-item history; expect one `response.create`, sent after the last history event.
- AC-17 WHEN `response.done` with status `completed` arrives for that response, the system shall return the concatenated text of its `response.output_text.delta` events as the sample's response (F6, F17). — proof: red-first unit — verify: a fake server streaming deltas "Of", "ten", "!" then a completed `response.done`; expect "Often!".
- AC-36 IF `response.done` arrives with status `cancelled`, THEN the system shall fail that attempt and log one line for it, never returning the partial text (F17). — proof: red-first unit — verify: a fake server streaming "Of" then a cancelled `response.done`; expect the attempt to raise, one logged line, and no returned text.
- AC-18 IF the server sends an event type the client does not handle, THEN the system shall ignore it and continue the sample (F5). — proof: red-first unit — verify: inject `conversation.context.summarized` and a made-up type mid-stream; expect the same returned text as without them.

Failure handling
- AC-19 IF an `error` event arrives at any point in a sample, THEN the system shall fail that attempt with an error naming the error type, and log one line for the event. — proof: red-first unit — verify: a fake server that sends `error` type `voice_output_task_ongoing` after `response.create`; expect the attempt to raise, and one logged line naming that type.
- AC-20 IF the connection closes before `response.done`, THEN the system shall fail that attempt with an error naming the close code, or the terminal event that preceded the close, and log one line for the failed attempt (F5, F8, F13, F21). — proof: red-first unit — verify: four runs where the fake server closes with 4429, 3000 and 1013, and once after `session.idle_timeout`; expect each attempt to raise, naming that code or event, with one logged line each.
- AC-21 IF `response.done` has not arrived within 60 s of the attempt opening its connection, THEN the system shall close the connection, fail that attempt, and log one line for the timeout. — proof: red-first unit — verify: a fake server that never sends `response.done`, on a controllable clock; expect a failure at 60 s, a closed connection and one logged timeout line.
- AC-22 IF the API key is missing, empty, or still the unexpanded placeholder `${BOSON_API_KEY}`, THEN the system shall fail before opening any connection, with a message that names `BOSON_API_KEY`. — proof: red-first unit — verify: three runs (unset, empty, literal placeholder) against a fake server; expect each to fail with zero connection attempts and a message containing "BOSON_API_KEY".
- AC-23 The system shall never write the API key into a log line, an error message or a response row. — proof: red-first unit — verify: run the AC-19, AC-20 and AC-21 failure paths with a sentinel key; expect the sentinel in none of the captured output.
- AC-38 The system shall behave as AC-1 to AC-37 require on every version of the WebSocket library that the `realtime` extra allows, from its declared minimum to the newest, including reporting the close code (AC-20). — proof: red-first unit — verify: run the offline suite once with the declared minimum version and once with the newest release; expect both green, with the 1013 close reported by code in both.

Runner and config (PR footprint)
- AC-24 WHEN the inference runner is started with backend `higgs-realtime`, the system shall run samples through the Higgs client, using the run's model and API key. — proof: red-first unit — verify: start the runner's client construction with backend `higgs-realtime`; expect a Higgs client carrying the given model and key.
- AC-25 WHEN the inference runner is started with backend `openai-realtime`, the system shall build the existing OpenAI realtime client with the same arguments as before this change. — proof: red-first unit — verify: build with backend `openai-realtime` on the PR branch and on upstream main; expect the same client type and the same constructor arguments.
- AC-26 The PR shall change exactly three files: a new Higgs client, a new `configs/higgs-realtime.yaml`, and the inference runner. In the runner, the only existing line that changes is the backend-choices line, which gains `higgs-realtime`, and the only other change is one added dispatch branch. The runner's module docstring stays as it is. — proof: e2e — verify: run by the main session, since the agent guard denies the repository diff to read-only agents; list the PR's changed files and read the runner diff; expect three files, one modified line (the choices line) and one added branch, and nothing else.
- AC-27 The `configs/higgs-realtime.yaml` model config shall set backend `higgs-realtime`, model `higgs-realtime`, the API key from `${BOSON_API_KEY}`, `max_new_tokens` 4096 and `max_workers` 1. — proof: red-first unit — verify: load the config; expect those five values.

Smoke run (P0 done-condition)
- AC-28 WHEN the runner runs with `configs/higgs-realtime.yaml`, `--max-workers 1`, `--limit 10` and `--output responses/higgs-realtime.jsonl`, the system shall write exactly 10 rows to that file. The subset is the runner's first 10 samples. — proof: e2e — verify: live run with that exact command; count the lines in the output file; expect 10.
- AC-29 WHEN the AC-28 smoke run completes, the system shall have written every row with the runner's keys `sample_id`, `conversation_id`, `interruption_type`, `turn_depth` and `response`. — proof: e2e — verify: parse each line; expect all five keys present in all 10 rows.
- AC-30 WHEN the AC-28 smoke run completes, the system shall have written a `response` that is non-empty after trimming whitespace, in every row. — proof: e2e — verify: parse each line; expect 10 non-empty responses.
- AC-31 WHEN the AC-28 smoke run completes, the runner shall report 10 responses saved and 0 failures. — proof: e2e — verify: the runner's final stderr line reads "10 responses saved to responses/higgs-realtime.jsonl, 0 failures."
- AC-32 WHEN the AC-28 smoke run completes, the run log shall contain zero failed-attempt lines (AC-19, AC-20, AC-21, AC-34, AC-36), including those from attempts the runner retried. — proof: e2e — verify: search the captured stderr of the run for those log lines; expect zero matches.
- AC-33 The system shall never send a `system`-role conversation item (F3). — proof: red-first unit — verify: run a sample with a non-empty system message; expect zero items with role `system` among the client's messages.

## Requirements coverage

| R | requirement | source | AC |
|---|---|---|---|
| R-1 | The smoke subset produces a response row per sample with no protocol errors | brief (BRIEF.md P0) | AC-28, AC-29, AC-30, AC-31, AC-32 |
| R-2 | User audio streams through `input_audio_buffer.append` (≤ 1 MiB) plus commit, never as `conversation.item.create` audio | brief; F3, F4 | AC-7, AC-8, AC-9 |
| R-3 | No waiting for `session.created` before `session.update` | brief; F1 | AC-1, AC-6 |
| R-4 | No waiting for `conversation.item.done` | brief; F5 | AC-15 |
| R-5 | Assistant history items use `text` | brief; F3 | AC-11, AC-12 |
| R-6 | Every user turn as audio, assistant turns as text, in history order, turn detection null | Glib, Q1; F16, F24 | AC-4, AC-10, AC-13, AC-14, AC-16 |
| R-7 | Text output, as the benchmark contract returns text | brief; F6 | AC-3, AC-17 |
| R-8 | The system message reaches the model | brief (benchmark contract); F3, F20 | AC-2, AC-33 |
| R-9 | 60 s per sample attempt, then failure and runner retry | Glib, Q2 | AC-21 |
| R-10 | `max_new_tokens` becomes the session's `max_output_tokens` | Glib, Q3 | AC-5 |
| R-11 | Smoke subset is the runner's first 10 samples | Glib, Q4; planner default, 2026-10-24 | AC-28, AC-31 |
| R-12 | One worker for Higgs: explicit in the smoke command, documented in the config | Glib, Q5 and worker answer, 2026-10-24 | AC-27, AC-28 |
| R-13 | PR = new client + YAML + one backend choice and one dispatch branch, small and reviewable | Glib, runner-edit answer; reuse-map | AC-24, AC-26, AC-27 |
| R-14 | The existing OpenAI realtime client keeps working unchanged | brief | AC-25, AC-26 |
| R-15 | Protocol errors, closes and unknown events are handled per the documented protocol | F5, F13, F14, F21 | AC-18, AC-19, AC-20, AC-32 |
| R-16 | A missing or unexpanded key fails before connecting | accepted proposal, 2026-10-24 | AC-22, AC-23 |
| R-17 | Smoke responses are non-empty | accepted proposal, 2026-10-24 | AC-30 |
| R-18 | A user WAV with zero samples fails the attempt with a log line | Glib, empty-WAV answer, 2026-10-24 | AC-34 |
| R-19 | A cancelled response fails the attempt; partial text is never a success | Glib, cancelled answer, 2026-10-24; F17 | AC-36, AC-17 |
| R-20 | Authentication as documented for server-side clients | Glib, protocol-facts answer; F23 | AC-37 |
| R-21 | Temperature is not sent; server default applies | Glib, worker answer; planner default; F20 | AC-35 |
| R-22 | Works on every WebSocket library version the `realtime` extra allows | main session, 2026-10-24 (follows AC-26: no dependency change) | AC-38 |

## Edge cases

- A user WAV longer than about 15 s exceeds one append (F4). It is split into several appends before a single commit (AC-8).
- A user turn without an audio file reaches the client as text and is replayed as text (AC-10), as in the existing client. A turn that has a WAV reaches the client as audio only, with its text dropped by the runner. The client therefore has no text fallback for it.
- A user turn whose WAV decodes to zero samples fails the attempt (AC-34). The runner retries, and the sample ends as failed.
- An interrupted assistant turn arrives already truncated by the dataset loader. It is replayed as given, never restored to the full utterance.
- An empty assistant turn sends nothing (AC-12).
- A history that starts with an assistant turn is replayed in order like any other.
- Live replay order differs from history order, or a response starts before `response.create` (AC-14 fails). This is an implementer blocker. The spec is updated to "prior user turns as text, interrupting turn as audio" (Q1 option b), and the plan is re-reviewed. The code does not fall back silently.
- `response.done` with status `cancelled` fails the attempt (AC-36).
- `max_new_tokens` above 4096 is clamped by the server (F20). The client sends the configured value unchanged.
- The server's 5-minute idle close (F8) may not apply with turn detection null (UNVERIFIED in `docs/boson-protocol.md`). The 60 s attempt bound (AC-21) holds either way.
- Exceeding the concurrency limit closes with 1013 (F21). That is a failed attempt (AC-20), and the runner retries.
- An attempt that fails and then succeeds on the runner's retry still writes a row. AC-32 catches the hidden failure.
- Run without `--max-workers 1`, the runner uses its own default worker count, not the config's. This is outside the smoke command (AC-28) and named in the PR description.
- With `--limit 10`, the runner takes the first 10 samples in dataset order, which may come from only one or two conversations. Accepted as the smoke subset (AC-28). It proves the protocol path, not interruption-type coverage.

## Non-functional requirements

- Performance: one sample attempt ends within 60 s (AC-21). The runner's three attempts bound a sample at about 3 minutes plus backoff.
- Cost: the smoke run is 10 samples, one worker (AC-28). Output is capped per response by `max_output_tokens` (AC-5). The client does not rely on per-response usage, since docs and wire disagree on it (F2). Any cost figure shown anywhere is computed from F12 and gets a `docs/CLAIMS.md` row. No new LLM call beyond the model under test.
- Security and privacy: the API key comes from the environment, is checked before connecting (AC-22), travels only as F23 describes (AC-37) and never appears in output (AC-23). Model output is untrusted and flows into the judge's prompt (see Untrusted inputs). No user data beyond the public dataset is sent.
- Accessibility: none beyond existing (no UI).
- i18n: none beyond existing.
- Reliability: every protocol error, early close, cancelled response, timeout or empty audio fails the attempt (AC-19 to AC-21, AC-34, AC-36), so the runner's existing retry handles it. A partial text is never returned as a success. Concurrency stays at 1 until the F21 limit is known. The client works across the allowed WebSocket library range (AC-38).

## Workflows and module communication

One sample attempt, including what happens when the server errors, cancels, closes or goes silent. The client never waits for `session.updated` or `conversation.item.done`.

```mermaid
sequenceDiagram
  participant R as IHBench runner
  participant C as Higgs client
  participant H as Higgs Realtime
  R->>C: system message, history, generation config
  alt key missing or unexpanded
    C-->>R: fail before connecting
  else key present
    C->>H: open WebSocket (auth per F23)
    C->>H: session.update (model, instructions, text, turn detection null, max_output_tokens)
    H-->>C: session.created
    loop each history turn, in order
      alt user turn with audio
        C->>H: input_audio_buffer.append (1..n chunks)
        C->>H: input_audio_buffer.commit
        H-->>C: input_audio_buffer.committed
      else user turn as text
        C->>H: conversation.item.create (input_text)
      else assistant turn with text
        C->>H: conversation.item.create (text)
      end
    end
    C->>H: response.create
    H-->>C: response.output_text.delta (many)
    alt response.done completed within 60 s
      H-->>C: response.done (completed)
      C-->>R: response text
    else response.done cancelled
      C-->>R: fail attempt (cancelled)
    else error event
      C-->>R: fail attempt (error type)
    else close or terminal event
      C-->>R: fail attempt (close code or event)
    else 60 s pass
      C->>H: close
      C-->>R: fail attempt (timeout)
    end
  end
  Note over R: on failure the runner retries, up to 3 attempts, then counts the sample as failed
```

An audio turn with zero samples fails the attempt before anything is sent for it (AC-34). It is left out of the diagram to keep it readable.

Who calls whom across the PR boundary:

```mermaid
flowchart LR
  yaml["Higgs model config"] --> runner[Inference runner]
  runner -- "backend higgs-realtime" --> higgs[Higgs client]
  runner -- "backend openai-realtime (unchanged)" --> oai[OpenAI realtime client]
  higgs -- WebSocket --> api[Higgs Realtime API]
  api -- "error / cancel / close / silence" --> higgs
  higgs -- "text or failure" --> runner
  runner --> jsonl[(responses JSONL)]
  jsonl --> judge[RQ judge, unchanged]
  jsonl --> factory[P1 Eval Card, this repo]
```

## Contracts

- Runner backend value: `higgs-realtime`, added to the existing list. No existing value changes meaning.
- Model config `configs/higgs-realtime.yaml`: the keys the runner already reads (`backend`, `model`, `api_key`, `max_new_tokens`, `max_workers`), with the values in AC-27. No new keys. `max_workers` does not take effect, because the runner's command-line default wins. It is kept as documentation, and the smoke command passes `--max-workers 1`.
- Smoke command: the AC-28 command with `--max-workers 1`. This is the P0 done-condition.
- Client contract: the same as every IHBench model client. Inputs are a system message, an ordered history of user (audio or text) and assistant (text) turns, and a generation config, of which only `max_new_tokens` is used. The output is the assistant's text, or a raised failure. A failure never comes back as an empty or partial string.
- Responses file: unchanged runner format. One JSON object per line with `sample_id`, `conversation_id`, `interruption_type`, `turn_depth`, `response`. This repo consumes it read-only.
- Wire protocol: as cited (F1, F3, F4, F5, F6, F13, F14, F16, F17, F20, F21, F23, F24). The spec never restates a fact.

## Inputs and provenance

- System message, history turns and sample metadata [reused: IHBench dataset `bosonai/ihbench`, through the existing loader]
- User turn audio, as WAV files [reused: IHBench dataset audio cache]
- Audio as 24 kHz PCM16 mono [deterministic: client-side audio conversion]
- `max_new_tokens`, model, key placeholder [reused: model config plus runner arguments]
- Worker count [reused: runner argument `--max-workers`, set to 1 in the smoke command]
- API key [reused: environment `BOSON_API_KEY`]
- Assistant response text [new: 1 LLM call per sample attempt, the model under test (Higgs Realtime)]

## Untrusted inputs

- Dataset transcripts and audio, downloaded from Hugging Face. They are sent to the model as data only. They never pick an endpoint, a file path outside the audio cache, or a session field other than content. Audio that decodes to nothing fails the attempt (AC-34).
- Server events. Unknown types are ignored (AC-18). Error payloads and close reasons are logged by type or code, never executed or used to choose behaviour beyond failing the attempt.
- Model output. It is written verbatim into the responses file and later placed in the RQ judge's prompt, so it is a prompt-injection path into the judge. The client neither interprets nor alters it. Judge hardening is out of scope (upstream judge, unchanged), and the risk goes into the PR description.
- Config values after environment expansion, notably the key: validated before use (AC-22), sent only as F23 describes (AC-37) and never echoed (AC-23).

## Open questions

None open. Resolved on 2026-10-24:
- How text items are observed in AC-14: the order check covers audio items only, and the live event log records whatever acknowledgement text items get (planner default).
- A WAV with zero samples fails the attempt (Glib, AC-34).
- The smoke subset is the runner's first 10 samples (planner default, AC-28).
- Temperature is not sent (planner default and Glib's worker answer, AC-35).

## Traceability

| AC | proof | verify | step | test | commit |
|---|---|---|---|---|---|
| AC-1 | red-first unit | silent fake server; first client message is `session.update` | 3 | `test_first_message_is_session_update`, not run (file only on test branch); partial (C:174) | not in review evidence |
| AC-2 | red-first unit | first update has model `higgs-realtime`, instructions = system message | 3 | `test_session_update_model_and_instructions`, not run (file only on test branch); partial (C:89, C:91) | not in review evidence |
| AC-3 | red-first unit | first update `output_modalities` exactly `["text"]` | 3 | `test_session_update_text_only`, not run (file only on test branch); partial (C:90) | not in review evidence |
| AC-4 | red-first unit | first update has turn detection null at the F24 path, nowhere else | 3 | `test_turn_detection_null_at_f24_path_only`, not run (file only on test branch); partial (C:93; VAD effect rests on AC-14) | not in review evidence |
| AC-5 | red-first unit | `max_new_tokens` 4096 becomes `max_output_tokens` 4096 | 3 | `test_max_output_tokens_from_max_new_tokens`, not run (file only on test branch); partial (C:92) | not in review evidence |
| AC-6 | red-first unit | only `session.created` sent; replay starts | 4 | `test_replay_starts_after_session_created_only`, not run (file only on test branch); partial (C:175) | not in review evidence |
| AC-7 | red-first unit | three audio turns; no audio in any item create | 4 | `test_no_audio_in_item_create`, not run (file only on test branch); partial (C:107-117, C:180) | not in review evidence |
| AC-8 | red-first unit | 40 s WAV; ≥ 2 appends ≤ 1 MiB each, one commit | 4 | `test_long_wav_split_into_appends_then_one_commit`, not run (file only on test branch); partial (C:57-60, C:179-181; 2-append live sample ac608127_1 succeeded) | not in review evidence |
| AC-9 | red-first unit | 2.0 s 16 kHz stereo WAV becomes 96,000 bytes ± 1 frame | 4 | `test_audio_resampled_to_24k_mono_pcm16`, not run (file only on test branch); partial (C:102, helper not opened) | not in review evidence |
| AC-10 | red-first unit | user turn as text becomes one `input_text` item | 4 | `test_text_user_turn_is_input_text_item`, not run (file only on test branch); partial (C:106-111) | not in review evidence |
| AC-11 | red-first unit | assistant turn becomes a `text` item; no `output_text` | 4 | `test_assistant_turn_is_text_item`, not run (file only on test branch); partial (C:112-117) | not in review evidence |
| AC-12 | red-first unit | empty assistant turn sends nothing | 4 | `test_empty_assistant_turn_sends_nothing`, not run (file only on test branch); partial (C:112) | not in review evidence |
| AC-13 | red-first unit | `committed` delayed 200 ms; next item waits | 4 | `test_next_item_waits_for_committed`, not run (file only on test branch); partial (C:181-182) | not in review evidence |
| AC-14 | e2e | live multi-turn sample; audio `previous_item_id` chain matches history, no response before `response.create`, text-item acks logged | 8 | `tests/live_replay_order.py`, no run in review evidence; unverifiable (main session, live) | not in review evidence |
| AC-15 | red-first unit | no `conversation.item.done` ever; sample completes | 4 | `test_completes_without_item_done`, not run (file only on test branch); partial (no item.done wait in C) | not in review evidence |
| AC-16 | red-first unit | 5-item history; one `response.create` after the last item | 4 | `test_one_response_create_after_last_item`, not run (file only on test branch); partial (C:187) | not in review evidence |
| AC-17 | red-first unit | deltas "Of","ten","!" + completed `response.done` return "Often!" | 5 | `test_returns_concatenated_deltas_on_completed`, not run (file only on test branch); partial (C:154-155, C:192-194) | not in review evidence |
| AC-18 | red-first unit | unknown events injected; same text returned | 5 | `test_unknown_events_ignored`, not run (file only on test branch); partial (C:156) | not in review evidence |
| AC-19 | red-first unit | `error` event fails the attempt; one log line with its type | 5 | `test_error_event_fails_attempt`, not run (file only on test branch); partial (C:145-151, C:213) | not in review evidence |
| AC-20 | red-first unit | closes 4429 / 3000 / 1013 / after idle timeout each fail, naming the cause, one log line each | 5 | `test_close_fails_attempt_naming_cause`, not run; NOT MET: a close during `ws.send` escapes as raw `ConnectionClosedError` with no log line, reproduced on websockets 17.3 and 12.0 (correctness `repro_close_raw.py`); OPEN | not in review evidence |
| AC-21 | red-first unit | no `response.done`; failure, close and one log line at 60 s | 5 | `test_attempt_timeout_closes_and_fails`, `test_default_attempt_timeout_is_60s`, not run; NOT MET: close handshake runs past the bound, 1 s timeout took 11.0 s (17.3) / 31.0 s (12.0) (correctness `repro_timeout.py`); OPEN | not in review evidence |
| AC-22 | red-first unit | unset / empty / placeholder key; zero connections, message names `BOSON_API_KEY` | 3 | `test_bad_key_fails_before_connect`, not run (file only on test branch); partial (C:74-76) | not in review evidence |
| AC-23 | red-first unit | sentinel key absent from all failure output | 5 | `test_key_never_in_failure_output`, not run (file only on test branch); partial (C:80-81, key only at C:166; 12.x redirect finding NEEDS-GLIB) | not in review evidence |
| AC-24 | red-first unit | backend `higgs-realtime` builds the Higgs client with model and key | 6 | `test_runner_builds_higgs_client`, not run (file only on test branch); partial (R:47-50) | not in review evidence |
| AC-25 | red-first unit | backend `openai-realtime` builds the same client and args as upstream main | 6 | `test_runner_openai_realtime_unchanged`, not run (file only on test branch); partial (R:43-46) | not in review evidence |
| AC-26 | e2e | main session: PR file list = 3 files; runner diff = choices line modified + one added branch, docstring untouched | 8 | main-session `git diff upstream/main...feat/higgs-realtime-client`, run by security and correctness reviewers ("the 3-file diff"); partial: choices-line-plus-one-elif not confirmed by any reviewer | not in review evidence |
| AC-27 | red-first unit | config has the five values | 2 | `test_config_has_five_values`, not run (file only on test branch); partial (Y:1-5) | not in review evidence |
| AC-28 | e2e | live run with `--max-workers 1 --limit 10`; output has 10 lines | 8 | live smoke `responses/higgs-realtime.jsonl`; partial: correctness summary says 10 rows, no line-count command in evidence | not in review evidence |
| AC-29 | e2e | all 10 rows carry the five keys | 8 | live smoke, keys per row; unverifiable (not checked by any reviewer) | not in review evidence |
| AC-30 | e2e | all 10 responses non-empty after trim | 8 | live smoke, non-empty responses; unverifiable (not checked by any reviewer) | not in review evidence |
| AC-31 | e2e | final line "10 responses saved …, 0 failures." | 8 | live smoke, final stderr line; unverifiable (not checked by any reviewer) | not in review evidence |
| AC-32 | e2e | zero AC-19/20/21/34/36 failed-attempt lines in the run's stderr | 8 | `grep -c 'attempt failed' responses/higgs-realtime.stderr.log` -> 0; partial: send-side closes are never logged (AC-20 finding), so the count can miss retried failures | not in review evidence |
| AC-33 | red-first unit | non-empty system message; zero `system`-role items sent | 4 | `test_no_system_role_item`, not run (file only on test branch); partial (C:97-118) | not in review evidence |
| AC-34 | red-first unit | WAV with zero frames; attempt fails, nothing sent for that turn, one log line | 4 | `test_zero_sample_wav_fails_before_sending`, not run (file only on test branch); partial (C:103-104, C:203) | not in review evidence |
| AC-35 | red-first unit | runner temperature 1.0; no temperature field in any client message | 3 | `test_no_temperature_sent`, not run (file only on test branch); partial (C:85-95, C:180-187) | not in review evidence |
| AC-36 | red-first unit | "Of" then cancelled `response.done`; attempt fails, one log line, no text returned | 5 | `test_cancelled_response_fails`, not run (file only on test branch); partial (C:192-193) | not in review evidence |
| AC-37 | red-first unit | handshake carries the F23 auth header with the key; no key in the URL | 3 | `test_handshake_bearer_header_no_key_in_url`, not run (file only on test branch); partial (C:33, C:166, C:170) | not in review evidence |
| AC-38 | red-first unit | offline suite green on the minimum and the newest WebSocket library version; 1013 reported by code | 3, 5, 7 | `test_headers_kwarg_by_version`, `test_connect_uses_kwarg_of_installed_version`, neither venv suite run; NOT MET: AC-20 defect reproduced on 17.3 and 12.0, and on 12.x the Bearer key follows a cross-origin redirect (NEEDS-GLIB) | not in review evidence |

The red-first unit tests run against a fake WebSocket server and live on a separate branch of the fork, not in the PR (Glib, Q6). The e2e checks need `BOSON_API_KEY` and spend credits, except AC-26, which reads the PR diff and is run by the main session.

## Changelog

| date | change | why |
|---|---|---|
| 2026-10-24 | Spec created as draft, Full SDD 4/6 (create plus answers mode). | P0 of `docs/BRIEF.md`. Glib answered Q1–Q6 and the runner-edit question, and research added F14, F16, F20 and F21. After the live smoke the F2 wording was aligned (docs and wire disagree on usage). F1, F5 and F14 are now VERIFIED-RUN; ids unchanged. |
| 2026-10-24 | Status set to approved. | Approved by Glib in chat; written by the main session on his word because the editor change was not saved to disk. |
| 2026-10-24 | Update mode, planner blocker. The smoke command gains `--max-workers 1`, and the YAML `max_workers` becomes documentation only. New ACs: AC-34 (zero-sample WAV fails), AC-35 (no temperature sent), AC-36 (cancelled response fails), AC-37 (auth per F23), AC-38 (whole allowed WebSocket library range). AC-4 now cites F24. AC-14 checks audio order and that no response starts early. AC-26 is proven by the main session. AC-10 and the edge cases note that the runner drops a turn's text when a WAV exists. All four open markers were closed. Status left as approved. | `sdd-engineering:implementation-planner` returned needs-answers: the runner ignores YAML `max_workers` (CLI default 8 wins) and drops the text of WAV turns. Glib answered the worker, empty-WAV, cancelled-response and protocol-fact questions, and the planner's defaults closed the open markers. The plan needs re-review. |
| 2026-10-24 | traceability filled after review loop | Claude |
| 2026-10-24 | Status set to implemented by Glib after the review loop (`docs/plans/2026-10-24-ihbench-higgs-client.verify.md`): no must-close; close handling and close timeout fixed in `abd6bd9`. | Glib, in chat. |
