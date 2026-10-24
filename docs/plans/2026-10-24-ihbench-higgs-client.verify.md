# Verify: IHBench client for Higgs Realtime

Date: 2026-10-24
Plan: `docs/plans/2026-10-24-ihbench-higgs-client.md`
Spec: `specs/2026-10-24-ihbench-higgs-client.md`
Target: `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs`, branch `feat/higgs-realtime-client` (tests on `chore/higgs-realtime-client-tests`)
Fix report: no must-close findings. No code changed in the loop.

## Plan-verifier (verbatim)

# Plan Verification: IHBench client for Higgs Realtime
Target: working tree of /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs (feat/higgs-realtime-client, not re-confirmed)
Overall: gaps (only because no test could be run or read; no AC is contradicted by the code I read)
Counts: 0 met · 29 partial · 0 not met · 12 unverifiable · 0 confirmed-unmapped hunks

Files read:
- C = /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/ihbench/clients/higgs_realtime_client.py
- Y = /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/configs/higgs-realtime.yaml
- R = /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/scripts/run_inference_api.py

### Steps
| item | verdict | evidence |
|---|---|---|
| S0 fork and environments (main session) | unverifiable | Needs Glib's confirmation, main session only. Indirect: the fork path exists and the three PR files are readable. I did not check both branches or both venvs. |
| S1 red-first suite on the test branch | unverifiable | The file is not in the working tree. Reading it was denied: `git -C ... show chore/...:tests/...` returned "only read-only git subcommands are allowed". No red-run record was in my brief. |
| S2 config YAML | partial | Y:1-5 has exactly backend, model, api_key `${BOSON_API_KEY}`, max_new_tokens 4096, max_workers 1. `test_config_has_five_values` not run. |
| S3 client module, constructor, connect, session start | partial | C:33-38 constants; C:47-54 `_headers_kwarg`; C:66-78 constructor; C:85-95 `_session_update` (the plan's exact shape); C:165-175 connect then immediate send. Tests not run. |
| S4 replay plan and replay | partial | C:57-60 `_chunk_b64`; C:97-118 `_build_replay`; C:122-157 `_wait_for`; C:177-184 replay loop; C:187 single `response.create`. `test_chunk_b64_boundaries` and the other S4 tests not run. |
| S5 response, failures, timeout, logging | partial | C:186-194 delta collection and status check; C:145-151 error event; C:127-137 close handling; C:205-211 `wait_for` timeout; C:212-214 the single log site. The four S5 test-first tests were not read or run. |
| S6 runner backend choice and dispatch | partial | R:47-50 `elif args.backend == "higgs-realtime":` with a lazy import and `HiggsRealtimeClient(model_name=args.model, api_key=args.api_key)`. R:110 choices line gains `"higgs-realtime"` after `"openai-realtime"`. R:15 docstring still reads "Backends: openai, openai-realtime, gemini, vllm" (untouched). I could not run the diff to confirm nothing else changed. |
| S7 live AC-14 harness, both websockets versions, branch carry-over | unverifiable | `tests/live_replay_order.py` and the branch state are not in the feat working tree. `.venv-ws12` run is not in the guard (plan: main-session evidence). |
| S8 footprint, AC-14, smoke, PR (main session, live) | unverifiable | Main session only. Live, spends credits, and `git -C` is denied. |

### Acceptance criteria
| item | verdict | evidence |
|---|---|---|
| AC-1 | partial | C:174 `session.update` is sent right after connect, before any recv. Test not run. |
| AC-2 | partial | C:89 model, C:91 instructions. |
| AC-3 | partial | C:90 `output_modalities: ["text"]`. |
| AC-4 | partial | C:93 `{"audio": {"input": {"turn_detection": None}}}`, and no other `turn_detection` key in the file. The VAD effect is proven live by AC-14, which is a main-session item. |
| AC-5 | partial | C:92 `max_output_tokens = config.max_new_tokens`. |
| AC-6 | partial | C:175 waits for `session.created` only. `session.updated` is never awaited. |
| AC-35 | partial | `grep temperature` finds nothing in C by reading; no temperature key in any built message (C:85-95, C:180-187). |
| AC-37 | partial | C:166 `Authorization: Bearer`, C:170 URL is the constant `wss://api.boson.ai/v1/realtime` (C:33) with no key in it. The kwarg is chosen at C:165. |
| AC-7 | partial | The only `conversation.item.create` payloads are text items (C:107-117). Audio goes only via `input_audio_buffer.append` (C:180). |
| AC-8 | partial | C:57-60 chunks at most 1,048,576 chars, a multiple of 4. C:179-181 sends the appends and then exactly one commit. |
| AC-9 | partial | C:102 reuses `_wav_to_pcm24k_b64` from the OpenAI client (C:31) as the plan specified. I did not open the helper, and its output is not run-verified. |
| AC-10 | partial | C:106-111 user text becomes an `input_text` item. |
| AC-34 | partial | C:103-104 raises `user turn {i} audio has zero samples`. C:203 builds the replay before connecting, and C:212-214 logs it. The check relies on an empty PCM giving an empty b64 string, which I did not verify in the helper. |
| AC-11 | partial | C:112-117 assistant item with content type `text`. |
| AC-12 | partial | C:112 `and msg.content` skips an empty assistant turn. |
| AC-13 | partial | C:181-182 commit, then `_wait_for committed` before the next step. |
| AC-14 | unverifiable | e2e live, main session. |
| AC-15 | partial | `conversation.item.done` is never awaited in C. |
| AC-16 | partial | C:187 exactly one `response.create`, after the loop. |
| AC-17 | partial | C:154-155 collects `delta` only after `response.create` (collect=True at C:186). C:192-194 returns the joined text on `completed`. |
| AC-36 | partial | C:192-193 non-completed status (including cancelled) raises, and the partial text is not returned. C:213 logs. |
| AC-18 | partial | C:156 returns only on the awaited type. All other types fall through. |
| AC-19 | partial | C:145-151 raises `error event <type> (<code>)`, never the message text. C:213 logs once. |
| AC-20 | partial | C:127-137 names `close code N`, or `after <session.idle_timeout / max_duration_reached>`, or `no close frame`. Logged at C:213. Behaviour on websockets 12.0 not run. |
| AC-21 | partial | C:34 default 60.0; C:205-211 `asyncio.wait_for` over connect through `response.done`; the exit stack closes the connection; one logged line containing "(timeout)". |
| AC-22 | partial | C:74-76 raises ValueError naming `BOSON_API_KEY` for None (no env), empty, whitespace, or the `${BOSON_API_KEY}` placeholder, at construction before any connection. |
| AC-23 | partial | Messages are built only from event type, code, status, close code, exception class (C:104, C:136, C:151, C:172, C:193). The key is stored in `_api_key` and used only at C:166. `__repr__` (C:80-81) omits it. |
| AC-38 | partial | C:47-54 maps major >= 14 to `additional_headers`, else `extra_headers`. C:131 reads `e.rcvd` safely when it is None. Neither venv run was possible: file not in working tree, and `.venv-ws12` is not in the guard. |
| AC-24 | partial | R:47-50 builds `HiggsRealtimeClient` from the run's model and api_key. |
| AC-25 | partial | R:43-46 the openai-realtime branch reads identically to the plan's reference (`model_name`, `api_key`, `reasoning_effort`). I cannot diff it against upstream. |
| AC-26 | unverifiable | Main session (`git -C diff --name-only`); denied to me. Indirect only: R:15 docstring unchanged, R:110 includes the new choice, R:47-50 is one added `elif`. |
| AC-27 | partial | Y:1-5 matches the five values. The key is written `${BOSON_API_KEY}` unquoted, which YAML reads as a plain string. |
| AC-28 | unverifiable | Live smoke, main session. |
| AC-29 | unverifiable | Live smoke, main session. |
| AC-30 | unverifiable | Live smoke, main session. |
| AC-31 | unverifiable | Live smoke, main session. |
| AC-32 | unverifiable | Live smoke, main session. The log prefix `higgs-realtime attempt failed:` is in place at C:35 and C:213. |
| AC-33 | partial | `_build_replay` (C:97-118) has no branch for the system role, so no system item is sent. |

### Contracts & data
| item | verdict | evidence |
|---|---|---|
| C1 runner backend value `higgs-realtime` at the choices line | partial | R:110 (line moved from the plan's "106" because of the added elif; plan lines refer to upstream). |
| C2 YAML has exactly the 5 keys, no `temperature` | partial | Y:1-5. |
| C3 client contract: `generate(...) -> str`, raises `HiggsRealtimeError`, ValueError at construction | partial | C:216-223, C:43-44, C:75-76. Only `config.max_new_tokens` is used (C:92). |
| C4 log contract: one WARNING per failed attempt, prefix `higgs-realtime attempt failed:` | partial | C:35, C:213 (`_log.warning("%s", err)`). It is the only log call in the file. |
| C5 responses file format unchanged | partial | R:89-98 unchanged runner row format, as far as the read range shows. |
| C6 no schema, migration or message catalog | met | None in the three files read. (Weak: I did not see the full diff stat.) |

### Checks
| item | command | exit | result line | verdict |
|---|---|---|---|---|
| K1 offline suite on `.venv` | `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest .../tests/test_higgs_realtime_client.py` | not run | test file absent from the working tree (Read: "File does not exist") | unverifiable |
| K2 offline suite on `.venv-ws12` (AC-38 minimum) | `.../.venv-ws12/bin/python -m pytest ...` | not run | file absent; the command is not in the guard | unverifiable (main session) |
| K3 architecture check | n/a | n/a | n/a | unverifiable (architecture-review:architecture-reviewer) |
| K4 security review | n/a | n/a | n/a | unverifiable (security reviewer) |
| K5 AC-26 diff, AC-14 harness, live smoke, code review | `git -C ... diff` | denied | "agent-guard: only read-only git subcommands are allowed" | unverifiable (main session) |

### Unmapped changes
None found in the three files I read. Every region of C maps to S3-S5, Y to S2, and R:47-50 and R:110 to S6. I could not run the diff to prove the runner has no other changed line: the `git -C` diff was denied. Reading R:1-125 showed nothing else obviously changed.

Must-close: none. No red check was run, and no AC the plan marks implemented is contradicted by the code.

## Reconciliation with the other lenses

The plan-verifier was denied `git -C` and could not read the test branch. The security and correctness reviewers did run `git diff upstream/main...feat/higgs-realtime-client` and `git show chore/higgs-realtime-client-tests:tests/test_higgs_realtime_client.py`. Their evidence moves these verdicts in the spec's Traceability table:

- AC-20: partial -> **not met** (correctness repro, close during send escapes raw and unlogged on 17.3 and 12.0).
- AC-21: partial -> **not met** (correctness repro, timeout overruns the bound).
- AC-38: partial -> **not met** (AC-38 includes AC-20 close reporting; the defect reproduces on both versions; plus the 12.x redirect finding).
- AC-26: unverifiable -> partial (3-file diff seen by security; runner hunks not confirmed by any reviewer).
- AC-28: unverifiable -> partial (correctness summary says 10 rows; no line-count command in evidence).
- AC-32: unverifiable -> partial (`grep -c` -> 0, but send-side closes never reach the log).

Final AC tally over the spec's 38 ACs: **0 met, 3 not met, 31 partial, 4 unverifiable** (AC-14, AC-29, AC-30, AC-31). This differs from the plan-verifier's "29 partial / 12 unverifiable", which also counted steps and contracts and had no diff access.

## Findings

| # | lens | severity | file:line | finding | status |
|---|---|---|---|---|---|
| 1 | security + correctness | should | `ihbench/clients/higgs_realtime_client.py:197` (security) / `:174` (correctness) | `ws.send` calls in `_run` are not wrapped. A server close mid-replay raises raw `ConnectionClosedError`: no `higgs-realtime attempt failed:` line (breaks AC-20, blinds AC-32), an `error` event sent before the close is lost, and the close reason text reaches runner stderr (spec "Untrusted inputs": close reasons by code only). Reproduced on 17.3 and 12.0 (`repro_close_raw.py`). Fix: wrap the send section in `except websockets.exceptions.ConnectionClosed` and raise the same `HiggsRealtimeError` `_wait_for` builds; add an offline test where `FakeConnection.send` raises `close_error(1013)`. | OPEN |
| 2 | correctness | should | `ihbench/clients/higgs_realtime_client.py:168` | Timeout overruns AC-21: after `wait_for` cancels, the close handshake runs to `close_timeout`. `attempt_timeout_s=1.0` took 11.0 s (17.3) and 31.0 s (12.0); real attempts about 70 s / 90 s. Fix: `close_timeout=1.0` on connect, measured 2.0 s / 4.0 s; on 12.0 the attempt is still bounded but runs past the bound. | OPEN |
| 3 | security | should | `ihbench/clients/higgs_realtime_client.py:170` | On websockets 12.x/13.x (legacy client, `extra_headers`), a cross-origin 3xx makes the client resend `Authorization: Bearer` to the new host; 17.x strips it. Needs a redirect from api.boson.ai or its edge. Fix options: raise the floor to `websockets>=14` (conflicts with AC-38 and touches `pyproject.toml`, outside AC-26's three files) or disable redirects / check the final host on the legacy path. | NEEDS-GLIB |
| 4 | security | nit | `ihbench/clients/higgs_realtime_client.py:165` | Server-controlled `error.type` / `error.code` go into the exception and log without length or character limits. Fix: truncate/sanitize, e.g. match `^[A-Za-z0-9_.-]{1,64}$`. | OPEN |
| 5 | plan | should | `tests/test_higgs_realtime_client.py` | Offline suite exists only on the test branch and no reviewer ran it on either venv; every test-backed AC stays partial. Main session must run K1 and K2. | OPEN |
| 6 | plan | should | `scripts/run_inference_api.py:47` | AC-26 "only the choices line plus one elif changed" not confirmed by any reviewer. Main session must read the runner hunk of the upstream diff. | OPEN |
| 7 | correctness | — | append frame size | Suspicion: a full 1,048,576-char append makes a 1,048,626-byte frame, just over 2**20. Refuted by live sample ac608127_1 (24 s `1.wav`, two appends) succeeding. | REFUTED |
| 8 | architecture | — | — | Pass, zero findings: client is the only `websockets` importer, reads only the `BOSON_API_KEY` env fallback; runner adds one lazy-import branch; YAML has the five keys. | — |

Nothing is FIXED: the fix report says no must-close findings and no change was made.

## Check commands and result lines

| command | by | result line |
|---|---|---|
| `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` | plan-verifier | not run: file absent from the feat working tree |
| `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv-ws12/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` | plan-verifier | not run: not in the guard |
| `git -C /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs diff upstream/main...feat/higgs-realtime-client` | plan-verifier, architecture | denied: "agent-guard: only read-only git subcommands are allowed" |
| `git diff upstream/main...feat/higgs-realtime-client` (+ `--stat`) | security, correctness | ran; security: "the 3-file diff" |
| `.venv` / `.venv-ws12` `python -c 'import websockets'` | security | 17.3 and 12.0 |
| `.venv/bin/python` and `.venv-ws12/bin/python repro_close_raw.py` | correctness | `RAISED websockets.exceptions ConnectionClosedError \| received 1013 (try again later); then sent 1013 (try again later) \| HiggsRealtimeError: False` on both |
| `.venv/bin/python` and `.venv-ws12/bin/python repro_timeout.py` (attempt_timeout_s=1) | correctness | `elapsed 11.0s` (17.3), `elapsed 31.0s` (12.0) |
| `.venv/bin/python` and `.venv-ws12/bin/python repro_timeout_fix.py` (close_timeout=1.0) | correctness | 2.0 s (17.3), 4.0 s (12.0) |
| `grep -c 'attempt failed' responses/higgs-realtime.stderr.log` | correctness | 0 |

Repro scripts: `/private/tmp/claude-503/-Users-Glebazzz-Claude-PROJECTS-Boson/54a21950-0ae7-4783-8209-424f69f6a17f/scratchpad/` (correctness reviewer).
