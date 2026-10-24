# Implementation Plan: Higgs Agent Factory (P1 gate + Eval Card, P2 demo page)
Status: ready
Spec: specs/2026-10-24-higgs-agent-factory.md (SPEC-2026-10-24-higgs-agent-factory)
Execution mode: multi-agent, chosen by the user
Save as: docs/plans/2026-10-24-higgs-agent-factory.md

## Minimal P1 slice (demoable alone)
Level 0 + level 1 (L1, L2, L3r, L3c; leave out the steps marked *cuttable*) + level 2 (J). That covers AC-1, AC-2, AC-3 (Specialist Training only; the other four wait on card texts), AC-4 to AC-8, AC-10 to AC-22, AC-24, AC-25, AC-27, AC-30 to AC-33, AC-46, AC-47 and AC-45. The output is a stored Eval Card from a real gate run, printed by `uv run python -m factory gate --template specialist-training`.
Cut first (in this order): the real generator adapter (step 6b), AC-9, AC-23, AC-28/29, AC-34, AC-48, AC-50/51, then all of L4 (P2). L5 (P3) is not planned: the spec has no ACs for it.

## Open questions & recommendations
- process: I planned despite open `[NEEDS CLARIFICATION]` markers (AC-20, AC-23, AC-26, AC-50, Open questions) because the brief asked for it and every marker is tagged non-blocking. blocking: no
- gap: judge model id. Default assumed: none. The Anthropic judge adapter reads `FACTORY_JUDGE_MODEL` from the composition root and refuses to start without it. Recommendation: `claude-sonnet-5-5` (latency matters for the live single scenario; 6 calls per run). ADR, needs Glib's sign-off. Blocks AC-45 only.
- gap: generator model and vendor. Default assumed: the template path is deterministic and makes no model call (assumed default, confirm); AC-1 and AC-2 are proven with a `BriefModel` double. Recommendation: Anthropic `claude-sonnet-5-5`, same key and SDK. ADR. Blocks only step 6b (cuttable).
- gap: new dependencies (pydantic, anthropic, httpx; P2: fastapi, uvicorn). Glib's global rule wants sign-off on every library. Recommendation: one ADR for all of them; lane 0 runs `uv add` only after approval. The anthropic SDK must be built with `max_retries=0` (the NFR forbids retries; the SDK retries by default). blocking: no for planning, yes for lane 0 execution.
- feasibility: pipecat-boson hides what the gate must measure. `_handle_interruption` (`vendor-ref/pipecat-boson/pipecat_boson/realtime/llm.py:658-664`) sends its own `response.cancel`; `_is_stale_response_event` (`:912`) drops later deltas of that response; 4429 and 1013 reach the caller only as a `push_error` string (`:598`). Default: the L2 adapter subclasses `BosonRealtimeLLMService` and taps raw traffic (`_dispatch_boson_server_event` inbound, `_ws_send` outbound, `_mark_websocket_disconnected` for `close_code`), turning it into our own domain events. This couples us to private API, so pin `==0.1.4`. Step 8 is a 30-minute spike; if it fails, the lane returns `blocked` (see Risks). blocking: no
- contradiction: AC-22 says "no other outgoing request", but whether the model continues after a `function_call_output` without `response.create` is not in `docs/boson-protocol.md` (F10 covers only the server tool). Default assumed: the P1 Specialist Training template has no client tools (assumed default, confirm), so AC-45 does not depend on this. The AC-22 test asserts the verify line literally; if the spike shows pipecat sends `response.create` after the output, the main session sends it back to spec-creator. blocking: no
- ambiguity: AC-20 (`rejected` vs `incomplete`). Default chosen so that no label is picked: on a refused voice the runner stops with `GateAborted(error_text)`, shows the text and stores no card. AC-20 holds (no scenario, error shown, not `released`); AC-33 does not apply because the run has no verdict. If Glib names a verdict, a card gets stored with it. blocking: no
- ambiguity: AC-50, whether `input_tokens` includes `cached_tokens`. Waits on answer (800 vs 1000 non-cached in the test). Steps 21b/21c are cuttable; until answered, AC-50/51 are not built and the card shows the AC-31 text or token counts only, never a token figure. blocking: no
- ambiguity: AC-29 aggregate (p50+max or p50+p95). Waits on answer, step 20b cuttable. blocking: no
- gap: AC-34 needs Spec B's result format (IHBench judge output), which is not described here. Waits on answer, step 22b cuttable; until then the card shows "not available". blocking: no
- contradiction: AC-31's text "Billed token cost: not measurable, the API returns no usage (F2)" claims to be "the phrasing in `docs/CLAIMS.md`", but `docs/CLAIMS.md:12` reads "Token cost: not measurable (F2)." The code uses the AC-31 string verbatim; spec or CLAIMS needs aligning (spec-creator / main session). blocking: no
- gap: AC-23 marker (does a missing expected call force below PASS). AC-19 already says the verdict comes from labels and completion only, so the plan records matched/not matched and does not change the verdict. Recommendation: close the marker in the spec with a reference to AC-19. blocking: no
- gap: Specialist Training content (instructions, 6 scenarios, rubrics) is not in the repo, and neither are the texts of the four other cards. Step 7 authors Specialist Training; Glib reviews the rubrics before AC-45, because they decide the verdict on stage. AC-3 for the other four waits on the card texts. blocking: no
- gap: the voice for the Realtime agent. F7 does not list presets. Default: `"default"`. Scripted user voices come only from the six F22 presets. blocking: no
- review-focus gaps (the spec can catch up): see Review focus; each item also counts as a gap here.

## Acceptance criteria (from the spec, verbatim)
- AC-1 WHEN a free-text brief of at most 1,000 characters is submitted, the system shall return either an Agent Spec that validates against the Agent Spec schema or the list of validation errors, each naming the failing field. — proof: red-first unit
- AC-2 IF a submitted brief exceeds 1,000 characters, THEN the system shall refuse it with a message that states the limit and shall make no model call. — proof: red-first unit
- AC-3 WHEN the user selects one of the five solution templates (Health Insurance, Fraud Detection, Customer Support, AI Receptionist, Specialist Training), the system shall produce an Agent Spec whose source field names that template and which validates against the schema. — proof: red-first unit
- AC-4 IF an Agent Spec has no budget limits, THEN the system shall refuse to start a gate run and name the missing limit fields. — proof: red-first unit
- AC-5 WHEN the Specialist Training template is selected, the system shall set its budget limits to exactly: 6 scenarios, 4 minutes of total audio (input plus output) per gate run, 1 judge call per scenario, and 3 minutes per live session. — proof: red-first unit
- AC-46 IF an Agent Spec has more scenarios than its own max-scenarios limit, THEN the system shall refuse to start a gate run and state both numbers. — proof: red-first unit
- AC-6 IF an Agent Spec's turn-detection settings contain `idle_timeout_ms` (rejected per F8), THEN schema validation shall fail and name that field. — proof: red-first unit
- AC-7 IF a client function tool in an Agent Spec has no mock behaviour, THEN schema validation shall fail and name that tool. — proof: red-first unit
- AC-8 WHEN a gate run needs audio for a scripted user turn, the system shall synthesise it with Higgs TTS 3 (F22) at most once per distinct text and voice and reuse the stored audio on later runs. — proof: red-first integration
- AC-9 IF TTS 3 synthesis fails for a user turn and a recorded audio file is supplied for that turn, THEN the system shall play the recording and mark that scenario's audio source as "recorded" on the Eval Card. — proof: red-first integration
- AC-10 IF a scripted user turn has neither synthesised nor recorded audio, THEN the system shall end the gate run with verdict `incomplete` and name the turn. — proof: red-first integration
- AC-11 WHEN a scenario ends, the system shall send the judge exactly one request with the scenario's rubric, the scripted user turn texts, the assistant transcript (F18) and the observed tool calls, and record the returned label (PASS, PARTIAL or FAIL), rationale and evidence quote. — proof: red-first unit
- AC-12 IF any scenario in a gate run is labelled PARTIAL or FAIL, THEN the system shall set the verdict to `rejected` and show, for each such scenario, its label, the rubric criteria it was judged against, the judge's rationale and the evidence quote. — proof: red-first unit
- AC-13 WHEN every scenario of a gate run that ran to the end is labelled PASS, the system shall set the verdict to `released`. — proof: red-first unit
- AC-14 IF the Boson session closes with code 4429 after an `insufficient_quota` error (F13) during a gate run, THEN the system shall set the verdict to `incomplete` with cause "quota refused" and shall not set `released`. — proof: red-first integration
- AC-15 IF the server sends `session.idle_timeout` (F8) during a gate run, THEN the system shall set the verdict to `incomplete` with cause "idle timeout". — proof: red-first integration
- AC-16 IF the Boson session closes with code 1013 (F21) during a gate run, THEN the system shall set the verdict to `incomplete` with cause "concurrency limit". — proof: red-first integration
- AC-17 IF the measured audio of a gate run (input plus output) reaches the Agent Spec's per-run audio limit before the last scenario ends, THEN the system shall stop the run and set the verdict to `incomplete` with cause "budget reached". — proof: red-first integration
- AC-18 IF the judge's reply does not carry exactly one of the labels PASS, PARTIAL or FAIL plus a rationale and an evidence quote, THEN the system shall set the verdict to `incomplete` with cause "judge reply invalid" and make no further judge call for that scenario. — proof: red-first unit
- AC-19 The system shall decide the verdict from scenario labels and run completion only, so IHBench RQ, TTFA and barge-in stop time never change it. — proof: red-first unit
- AC-20 IF the session configuration with the Agent Spec's voice is refused by the server (F7, F14), THEN the system shall stop before any scenario runs, show the server's error text, and shall not set `released`. [NEEDS CLARIFICATION: is this verdict labelled `rejected` (agent fault) or `incomplete`?] — proof: red-first integration
- AC-21 WHEN the model emits a `web_search` call with `executor: "server"` (F10), the system shall send no tool output and no response request for it, and shall record it as an observed tool call marked "server". — proof: red-first integration
- AC-22 WHEN the model calls a client function tool, the system shall answer with the mock output defined in the Agent Spec for that tool and perform no other action. — proof: red-first integration
- AC-23 WHEN a scenario that declares an expected tool call ends, the system shall record on the Eval Card whether a call with that tool name and the declared required arguments was observed. [NEEDS CLARIFICATION: does a missing expected call force the scenario below PASS regardless of the judge?] — proof: red-first unit
- AC-24 WHEN the server sends an event type the system does not know (F5), the system shall ignore it and continue the run. — proof: red-first unit
- AC-47 WHEN a scripted user turn is played, the system shall stream its audio at real-time pace (each second of audio sent over about one second) and follow it with streamed silence, never sending a turn in one burst. — proof: red-first integration
- AC-25 WHEN the last speech chunk (before the trailing silence) of a scripted user turn has been sent, the system shall record that turn's TTFA as the client-side time until the first `response.output_audio.delta` (F17) of the response that follows. — proof: red-first integration
- AC-26 WHILE a live session runs, the system shall record TTFA for every user turn, from the client's receipt of `input_audio_buffer.speech_stopped` (F15) to the first `response.output_audio.delta` (F17) of the response that follows. [NEEDS CLARIFICATION: live start point. `speech_stopped` receipt excludes the VAD silence window that the card's TTFA includes (AC-27), so live numbers will read lower than the card's; alternative is a client-side end-of-speech mark.] — proof: red-first integration
- AC-27 WHEN an Eval Card is produced, the system shall show TTFA p50 and p95 over all scripted turns of the run, the number of turns n, and a label stating that timing starts at the last user speech chunk sent and so includes the server VAD silence window (F8). — proof: red-first unit
- AC-48 The system shall compute the Eval Card's TTFA p50 and p95 from scripted gate-run turns only, never from live-session turns. — proof: red-first unit
- AC-28 WHEN an interrupting user turn is played over assistant audio, the system shall record barge-in stop time from the client sending the first interrupting audio chunk to the receipt of the last `response.output_audio.delta` carrying the interrupted response's id before its `response.done` (F17). — proof: red-first integration
- AC-29 IF the interrupted response's `response.done` has status `completed`, or no `response.done` for it arrives before the scenario ends, or its last audio delta arrived before the interrupting audio started, THEN the system shall record that turn's barge-in stop time as "not measured" and leave it out of the card's aggregate. — proof: red-first unit
- AC-30 WHEN an Eval Card is produced, the system shall show the estimated audio cost as measured input audio minutes times the F12 audio-input rate plus measured output audio minutes times the F12 audio-output rate, with both minute counts shown and the label "estimated from Boson's published per-minute rates". — proof: red-first unit
- AC-31 IF any `response.done` of a run carries no usage (F2), THEN the system shall show the token part of the cost as "Billed token cost: not measurable, the API returns no usage (F2)", the phrasing in `docs/CLAIMS.md`, and shall show no figure that includes token cost. — proof: red-first unit
- AC-50 WHEN every `response.done` of a run reported usage (F2), the system shall show the measured token cost as the run's non-cached input tokens × the F12 input-token rate + cached input tokens × the F12 cached-input rate + output tokens × the F12 output-token rate, with the three token counts and the label "measured from reported usage × Boson's published token rates". [NEEDS CLARIFICATION: whether `input_tokens` already includes `cached_tokens` (the smoke run had 0 cached), which decides the non-cached count; settle with a run that has cache hits.] — proof: red-first unit
- AC-51 WHEN a measured token cost is shown (AC-50), the system shall show it as the card's headline cost and still show the estimated audio cost (AC-30) as a separate line labelled as an estimate. — proof: red-first unit
- AC-32 The system shall not label any numeric cost figure as billed, actual or invoiced cost. — proof: red-first unit
- AC-33 WHEN a gate run ends with any verdict, the system shall store an Eval Card with every Eval Card field and the run's raw per-turn measurements under the run id, without overwriting an earlier card. — proof: red-first unit
- AC-34 WHERE an IHBench result for Higgs Realtime from Spec B is available, the system shall show its RQ pass rate labelled "model-level, IHBench samples" together with that result's source and date; otherwise it shall show "not available". — proof: red-first unit
- AC-35 WHEN a live session reaches the Agent Spec's live-session limit, the system shall close the session and tell the user the limit was reached. — proof: red-first integration
- AC-36 WHILE a live session runs for an agent whose latest Eval Card verdict is not `released`, the demo page shall show a visible "not released" label for the whole session. — proof: browser (main session)
- AC-52 WHEN the demo page reaches the gate step, the system shall show the stored full Eval Card of the agent's latest complete gate run, with its run id and timestamp. — proof: browser (main session)
- AC-53 WHEN the presenter runs one chosen scenario live from the demo page, the system shall show that scenario's label, rationale, evidence and TTFA, mark the result "single-scenario check", and leave the agent's verdict from its full gate run unchanged. — proof: red-first integration
- AC-37 The system shall never send a Boson or Anthropic API key to the demo page. — proof: red-first integration
- AC-38 WHEN the demo page opens, the system shall show the five template cards. — proof: browser (main session)
- AC-49 WHEN the user selects a template card on the demo page, the system shall show the Agent Spec generated from it. — proof: browser (main session)
- AC-39 WHILE a gate run is in progress, the demo page shall show which scenario is running and each finished scenario's label. — proof: browser (main session)
- AC-40 WHEN a gate run ends, the demo page shall show the Eval Card with the verdict written as a word, not by colour alone. — proof: browser (main session)
- AC-41 WHILE a live session runs, the demo page shall show each turn's TTFA as it is recorded, with a label naming where the live timing starts. — proof: browser (main session)
- AC-42 WHEN `input_audio_buffer.speech_started` (F15) arrives while assistant audio is playing in a live session, the demo page shall stop playing that response's audio. — proof: browser (main session)
- AC-43 WHEN `session.idle_timeout` (F8) arrives in a live session, the demo page shall say the session ended for inactivity and offer to start a new one. — proof: red-first integration
- AC-44 IF a live session closes with code 4429 (F13), THEN the demo page shall say the API quota was refused and shall not reconnect on its own. — proof: red-first integration
- AC-45 WHEN the gate runs on the Specialist Training agent against the live Boson API, the system shall produce a stored Eval Card with a verdict, TTFA p50/p95 with n ≥ 1, input and output audio minutes and the estimated audio cost. — proof: e2e

## Traceability
| AC | step | test | proof |
|---|---|---|---|
| AC-1 | 6 | `tests/test_generator.py::test_ac1_valid_output_and_missing_voice` | red-first unit |
| AC-2 | 6 | `tests/test_generator.py::test_ac2_overlong_brief_refused_no_call` | red-first unit |
| AC-3 | 7 | `tests/test_templates.py::test_ac3_each_template_valid_with_source` | red-first unit |
| AC-4 | 12 | `tests/test_gate_runner.py::test_ac4_missing_budget_refused_no_session` | red-first unit |
| AC-5 | 7 | `tests/test_templates.py::test_ac5_specialist_training_budget` | red-first unit |
| AC-6 | 2 | `tests/test_agent_spec_schema.py::test_ac6_idle_timeout_ms_rejected` | red-first unit |
| AC-7 | 2 | `tests/test_agent_spec_schema.py::test_ac7_client_tool_without_mock` | red-first unit |
| AC-8 | 13 | `tests/test_tts_cache.py::test_ac8_one_request_per_distinct_turn` | red-first integration |
| AC-9 | 13b | `tests/test_tts_cache.py::test_ac9_recording_fallback_marked_recorded` | red-first integration |
| AC-10 | 13 | `tests/test_gate_runner.py::test_ac10_no_audio_incomplete_names_turn` | red-first integration |
| AC-11 | 15 | `tests/test_judge.py::test_ac11_one_request_four_inputs_three_fields` | red-first unit |
| AC-12 | 18 | `tests/test_verdict.py::test_ac12_partial_rejects_with_failing_lines` | red-first unit |
| AC-13 | 18 | `tests/test_verdict.py::test_ac13_all_pass_released` | red-first unit |
| AC-14 | 9, 16 | `tests/test_runtime_session.py::test_ac14_4429_maps_quota_refused`, `tests/test_gate_runner.py::test_ac14_quota_refused_incomplete` | red-first integration |
| AC-15 | 9, 16 | `tests/test_runtime_session.py::test_ac15_idle_timeout_cause`, `tests/test_gate_runner.py::test_ac15_idle_timeout_incomplete` | red-first integration |
| AC-16 | 9, 16 | `tests/test_runtime_session.py::test_ac16_1013_concurrency_limit`, `tests/test_gate_runner.py::test_ac16_concurrency_limit_incomplete` | red-first integration |
| AC-17 | 16 | `tests/test_gate_runner.py::test_ac17_audio_budget_reached` | red-first integration |
| AC-18 | 15, 18 | `tests/test_judge.py::test_ac18_invalid_label_one_call`, `tests/test_verdict.py::test_ac18_judge_invalid_incomplete` | red-first unit |
| AC-19 | 18 | `tests/test_verdict.py::test_ac19_rq_and_ttfa_do_not_change_verdict` | red-first unit |
| AC-20 | 9, 16 | `tests/test_runtime_session.py::test_ac20_refused_voice_raises_with_text`, `tests/test_gate_runner.py::test_ac20_refused_voice_no_scenario_not_released` | red-first integration |
| AC-21 | 10 | `tests/test_runtime_session.py::test_ac21_server_web_search_no_reply` | red-first integration |
| AC-22 | 10, 16 | `tests/test_runtime_session.py::test_ac22_tool_output_sent`, `tests/test_gate_runner.py::test_ac22_client_tool_gets_mock` | red-first integration |
| AC-23 | 17b | `tests/test_gate_runner.py::test_ac23_expected_call_matched_and_not` | red-first unit |
| AC-24 | 16 | `tests/test_gate_runner.py::test_ac24_unknown_event_ignored` | red-first unit |
| AC-25 | 14 | `tests/test_playback.py::test_ac25_ttfa_from_last_speech_chunk` | red-first integration |
| AC-26 | 26 | `tests/test_live_session.py::test_ac26_live_ttfa_from_speech_stopped` | red-first integration |
| AC-27 | 19 | `tests/test_metrics.py::test_ac27_p50_p95_n_label` | red-first unit |
| AC-28 | 17c | `tests/test_playback.py::test_ac28_bargein_stop_time` | red-first integration |
| AC-29 | 20b | `tests/test_metrics.py::test_ac29_not_measured_excluded` | red-first unit |
| AC-30 | 21 | `tests/test_cost.py::test_ac30_audio_estimate_and_label` | red-first unit |
| AC-31 | 21 | `tests/test_cost.py::test_ac31_missing_usage_text_no_token_amount` | red-first unit |
| AC-32 | 21, 27 | `tests/test_cost.py::test_ac32_no_billed_actual_invoiced`, `tests/test_web.py::test_ac32_page_cost_block` | red-first unit |
| AC-33 | 22 | `tests/test_card_store.py::test_ac33_two_runs_two_cards` | red-first unit |
| AC-34 | 22b | `tests/test_card_store.py::test_ac34_rq_available_and_not` | red-first unit |
| AC-35 | 26 | `tests/test_live_session.py::test_ac35_live_limit_closes` | red-first integration |
| AC-36 | 28 | main-session browser check | browser (main session) |
| AC-37 | 27 | `tests/test_web.py::test_ac37_no_key_in_responses` | red-first integration |
| AC-38 | 28 | main-session browser check | browser (main session) |
| AC-39 | 28 | main-session browser check | browser (main session) |
| AC-40 | 28 | main-session browser check | browser (main session) |
| AC-41 | 28 | main-session browser check | browser (main session) |
| AC-42 | 28 | main-session browser check | browser (main session) |
| AC-43 | 27 | `tests/test_web.py::test_ac43_idle_timeout_message` | red-first integration |
| AC-44 | 27 | `tests/test_web.py::test_ac44_quota_no_reconnect` | red-first integration |
| AC-45 | 24 | `tests/test_e2e_gate.py::test_ac45_specialist_training_live` | e2e |
| AC-46 | 12 | `tests/test_gate_runner.py::test_ac46_too_many_scenarios` | red-first unit |
| AC-47 | 14 | `tests/test_playback.py::test_ac47_realtime_pace_then_silence` | red-first integration |
| AC-48 | 19b | `tests/test_metrics.py::test_ac48_scripted_only` | red-first unit |
| AC-49 | 28 | main-session browser check | browser (main session) |
| AC-50 | 21b | `tests/test_cost.py::test_ac50_measured_token_cost` | red-first unit |
| AC-51 | 21c | `tests/test_cost.py::test_ac51_token_headline_audio_separate` | red-first unit |
| AC-52 | 28 | main-session browser check | browser (main session) |
| AC-53 | 27 | `tests/test_web.py::test_ac53_single_scenario_check_keeps_verdict` | red-first integration |

## Red-first
- AC-1 → `tests/test_generator.py`: test_ac1_valid_output_and_missing_voice
- AC-2 → `tests/test_generator.py`: test_ac2_overlong_brief_refused_no_call
- AC-3 → `tests/test_templates.py`: test_ac3_each_template_valid_with_source (parametrised over 5; the 4 non-P1 cases are `xfail(strict=True, reason="card text pending")` until texts arrive)
- AC-4 → `tests/test_gate_runner.py`: test_ac4_missing_budget_refused_no_session
- AC-5 → `tests/test_templates.py`: test_ac5_specialist_training_budget
- AC-6 → `tests/test_agent_spec_schema.py`: test_ac6_idle_timeout_ms_rejected
- AC-7 → `tests/test_agent_spec_schema.py`: test_ac7_client_tool_without_mock
- AC-8 → `tests/test_tts_cache.py`: test_ac8_one_request_per_distinct_turn
- AC-9 → `tests/test_tts_cache.py`: test_ac9_recording_fallback_marked_recorded
- AC-10 → `tests/test_gate_runner.py`: test_ac10_no_audio_incomplete_names_turn
- AC-11 → `tests/test_judge.py`: test_ac11_one_request_four_inputs_three_fields
- AC-12 → `tests/test_verdict.py`: test_ac12_partial_rejects_with_failing_lines
- AC-13 → `tests/test_verdict.py`: test_ac13_all_pass_released
- AC-14 → `tests/test_runtime_session.py`: test_ac14_4429_maps_quota_refused; `tests/test_gate_runner.py`: test_ac14_quota_refused_incomplete
- AC-15 → `tests/test_runtime_session.py`: test_ac15_idle_timeout_cause; `tests/test_gate_runner.py`: test_ac15_idle_timeout_incomplete
- AC-16 → `tests/test_runtime_session.py`: test_ac16_1013_concurrency_limit; `tests/test_gate_runner.py`: test_ac16_concurrency_limit_incomplete
- AC-17 → `tests/test_gate_runner.py`: test_ac17_audio_budget_reached
- AC-18 → `tests/test_judge.py`: test_ac18_invalid_label_one_call; `tests/test_verdict.py`: test_ac18_judge_invalid_incomplete
- AC-19 → `tests/test_verdict.py`: test_ac19_rq_and_ttfa_do_not_change_verdict
- AC-20 → `tests/test_runtime_session.py`: test_ac20_refused_voice_raises_with_text; `tests/test_gate_runner.py`: test_ac20_refused_voice_no_scenario_not_released
- AC-21 → `tests/test_runtime_session.py`: test_ac21_server_web_search_no_reply
- AC-22 → `tests/test_runtime_session.py`: test_ac22_tool_output_sent; `tests/test_gate_runner.py`: test_ac22_client_tool_gets_mock
- AC-23 → `tests/test_gate_runner.py`: test_ac23_expected_call_matched_and_not
- AC-24 → `tests/test_gate_runner.py`: test_ac24_unknown_event_ignored
- AC-25 → `tests/test_playback.py`: test_ac25_ttfa_from_last_speech_chunk
- AC-26 → `tests/test_live_session.py`: test_ac26_live_ttfa_from_speech_stopped
- AC-27 → `tests/test_metrics.py`: test_ac27_p50_p95_n_label
- AC-28 → `tests/test_playback.py`: test_ac28_bargein_stop_time
- AC-29 → `tests/test_metrics.py`: test_ac29_not_measured_excluded
- AC-30 → `tests/test_cost.py`: test_ac30_audio_estimate_and_label
- AC-31 → `tests/test_cost.py`: test_ac31_missing_usage_text_no_token_amount
- AC-32 → `tests/test_cost.py`: test_ac32_no_billed_actual_invoiced; `tests/test_web.py`: test_ac32_page_cost_block
- AC-33 → `tests/test_card_store.py`: test_ac33_two_runs_two_cards
- AC-34 → `tests/test_card_store.py`: test_ac34_rq_available_and_not
- AC-35 → `tests/test_live_session.py`: test_ac35_live_limit_closes
- AC-37 → `tests/test_web.py`: test_ac37_no_key_in_responses
- AC-43 → `tests/test_web.py`: test_ac43_idle_timeout_message
- AC-44 → `tests/test_web.py`: test_ac44_quota_no_reconnect
- AC-46 → `tests/test_gate_runner.py`: test_ac46_too_many_scenarios
- AC-47 → `tests/test_playback.py`: test_ac47_realtime_pace_then_silence
- AC-48 → `tests/test_metrics.py`: test_ac48_scripted_only
- AC-50 → `tests/test_cost.py`: test_ac50_measured_token_cost
- AC-51 → `tests/test_cost.py`: test_ac51_token_headline_audio_separate
- AC-53 → `tests/test_web.py`: test_ac53_single_scenario_check_keeps_verdict

## Review focus
- A judge reply wrapped in prose or a code fence around otherwise valid JSON → `parse_judgment` takes only a strict JSON object; anything else counts as invalid. Pinned by `tests/test_judge.py::test_fenced_or_prose_reply_is_invalid` in step 15.
- Usage present but with a non-numeric or missing count (`"input_tokens": null`) → treated as "no usage" (spec, Untrusted inputs). Pinned by `tests/test_cost.py::test_non_numeric_usage_counts_as_missing` in step 21.
- Run id collision when two runs end within the same second → store opens with exclusive create, and the run id carries a uuid suffix. Pinned by `tests/test_card_store.py::test_same_second_runs_distinct_ids` in step 22.
- A recording path that escapes the recordings folder (`../../.env`), or any recording on a brief-sourced spec → validation error. Pinned by `tests/test_agent_spec_schema.py::test_recording_path_must_stay_in_recordings_dir` in step 2.
- A Boson server error text containing markup, shown on the demo page → rendered as text. Pinned by `tests/test_web.py::test_error_text_escaped` in step 27.

## Context read
- `CLAUDE.md:54-66`: Check table and guard parity; the plan adds no offline command, so `.claude/agent-guard.json` stays unchanged.
- `CLAUDE.md:84-89`: do-not-touch: `vendor-ref/` is never imported, `uv.lock` changes only through `uv add`, `.env` is never read into output.
- `CLAUDE.md:10-16`: Boson facts only from `docs/boson-protocol.md`; every stage number needs a `docs/CLAIMS.md` row.
- `docs/boson-protocol.md` F2, F7, F8, F10, F12, F13, F15–F18, F21, F22, F24, plus the UNVERIFIED list: these shaped the session adapter, the playback (stream PCM at 24 kHz, F22 `stream: true` + `pcm`) and the cost constants.
- `docs/reuse-map.md:8`: pipecat-boson is the runtime; never write our own Realtime client. This drives the tap-subclass design and the spike.
- `docs/reuse-map.md:10`, `vendor-ref/ProactBench/proactbench/types.py:10-21`: rubric shape `pass_criteria/partial_criteria/fail_criteria`; judgment `label/rationale/evidence`.
- `vendor-ref/pipecat-boson/pipecat_boson/realtime/llm.py:575-623, 658-664, 912-922, 371-402`: the receive loop, auto-cancel at barge-in, stale-delta filter and disconnect path that the adapter must tap.
- `vendor-ref/pipecat-boson/pipecat_boson/realtime/config.py:18-25, 147-199`: default turn-detection and session.update payload; Agent Spec fields map onto the constructor args.
- `pyproject.toml:17-25`: `package = false` and no `pythonpath`, so `import factory` from `tests/` needs `pythonpath = ["."]`.
- `tests/test_scaffold.py:35-46`: guard ⇔ Check-table parity test; a new `| none |` row needs a matching guard entry.
- `.gitignore:4`: `results/` is ignored, so stored cards and the TTS cache are local only.
- `docs/BRIEF.md:43-53`: P-order; never ship a half-done higher P over a solid lower one.
- No `.claude/rules/`, no `.claude/skills/`, no ADR folder, empty `factory/INSIGHTS.md`.

## Affected surfaces
- root → `pyproject.toml`, `uv.lock` (changed, via `uv add` + pytest `pythonpath`)
- factory → agent_spec → domain → `factory/agent_spec/models.py`, `validation.py` (new)
- factory → agent_spec → service → `factory/agent_spec/generator.py` (new); templates → `factory/agent_spec/templates/specialist_training.json`, `templates/__init__.py`, `templates/recordings/` (new)
- factory → ports → `factory/ports.py` (new)
- factory → gate → domain → `factory/gate/records.py`, `verdict.py`, `metrics.py`, `cost.py`, `card_builder.py`, `render.py`, `ihbench.py` (new)
- factory → gate → service → `factory/gate/runner.py`, `playback.py`, `judge.py`, `tts_cache.py` (new)
- factory → adapters → `factory/runtime/boson_session.py`, `factory/gate/tts_boson.py`, `factory/gate/judge_anthropic.py`, `factory/gate/card_store.py`, `factory/agent_spec/brief_anthropic.py` (new)
- factory → composition root / entry → `factory/composition.py`, `factory/__main__.py` (new)
- factory → P2 → `factory/live/session.py`, `factory/web/app.py`, `factory/web/static/index.html` (new)
- tests → `tests/conftest.py`, `tests/doubles.py`, `tests/fake_realtime_server.py`, `tests/test_*.py` (new)

## Constraints
- Boson behaviour only from cited F-ids; never from OpenAI Realtime. Source: `CLAUDE.md:10-13`. Every wire assumption in code carries an `# F<n>` comment; UNVERIFIED behaviour gets a live check, not a guess.
- `vendor-ref/` is never imported or edited. Source: `CLAUDE.md:86-87`. pipecat-boson comes from PyPI `==0.1.4`.
- `uv.lock` changes only via `uv add`. Source: `CLAUDE.md:88`. All adds happen in lane 0 (L4's web deps in L4, alone at its level).
- Secrets come only through the composition root (`factory/composition.py`) from env/`.env`; never printed, never sent to the page (AC-37). Source: `CLAUDE.md:51-52`, the security skill.
- Layering (project declares none, so the `engineering-paved-path:architecture-boundaries` defaults apply): domain (`agent_spec/models.py`, `gate/records.py`, `verdict.py`, `metrics.py`, `cost.py`, `card_builder.py`) imports no SDK; vendor SDKs (pipecat, anthropic, httpx) are imported only in adapters and in the composition root; services (`runner.py`, `generator.py`, `live/session.py`) receive ports, not env; composition only in `composition.py`; entries (`__main__.py`, `web/app.py`) parse, call one service and map.
- Untrusted input (the security skill): brief length-capped before any call; generator output and judge reply validated against schemas; model text passed to the judge inside delimited data blocks; tool arguments only select a mock; recording paths are bare filenames resolved inside `factory/agent_spec/templates/recordings/` and are rejected on brief-sourced specs; server error text rendered as text.
- No retries anywhere (spec NFR Reliability): anthropic client `max_retries=0`, httpx with no retry transport, no gate re-run, no reconnect on 4429.
- Live tests carry `@pytest.mark.live` and never enter the guard. Source: `CLAUDE.md:38, 65-66`.
- Python 3.12, ruff (E, F, I, B, UP; line 100). Source: `pyproject.toml:27-33`. Async tests run through `asyncio.run(...)` inside sync tests (no pytest-asyncio).
- Test names start with `test_ac<N>_` so plan-verifier can filter with `-k ac<N>`.

## Skills for the implementer
- all paths → none — project rules only (no `.claude/skills/`); `engineering-paved-path:engineering-insights` when starting/finishing in `factory/` (`CLAUDE.md:101`)

## Lanes
| lane | steps | owned paths | after |
|---|---|---|---|
| 0 | 1–3 | `pyproject.toml`, `uv.lock`, `factory/agent_spec/__init__.py`, `factory/agent_spec/models.py`, `factory/agent_spec/validation.py`, `factory/ports.py`, `factory/gate/__init__.py`, `factory/gate/records.py`, `factory/runtime/__init__.py`, `tests/conftest.py`, `tests/doubles.py`, `tests/fake_realtime_server.py`, `tests/test_agent_spec_schema.py`, `tests/test_contracts.py` | — |
| L1 | 6, 6b*, 7 | `factory/agent_spec/generator.py`, `factory/agent_spec/brief_anthropic.py`, `factory/agent_spec/templates/**`, `tests/test_generator.py`, `tests/test_templates.py` | 0 |
| L2 | 8–11 | `factory/runtime/boson_session.py`, `tests/test_runtime_session.py` | 0 |
| L3r | 12–17c | `factory/gate/runner.py`, `factory/gate/playback.py`, `factory/gate/judge.py`, `factory/gate/tts_cache.py`, `factory/gate/tts_boson.py`, `factory/gate/judge_anthropic.py`, `tests/test_gate_runner.py`, `tests/test_playback.py`, `tests/test_tts_cache.py`, `tests/test_judge.py` | 0 |
| L3c | 18–22b | `factory/gate/verdict.py`, `factory/gate/metrics.py`, `factory/gate/cost.py`, `factory/gate/card_builder.py`, `factory/gate/render.py`, `factory/gate/card_store.py`, `factory/gate/ihbench.py`, `tests/test_verdict.py`, `tests/test_metrics.py`, `tests/test_cost.py`, `tests/test_card_store.py` | 0 |
| J | 23–24 | `factory/composition.py`, `factory/__main__.py`, `tests/test_gate_wire.py`, `tests/test_e2e_gate.py` | L1, L2, L3r, L3c |
| L4 (P2, cuttable) | 25–28 | `pyproject.toml`, `uv.lock`, `factory/live/**`, `factory/web/**`, `tests/test_live_session.py`, `tests/test_web.py` | J |

DAG levels: 0 → {L1, L2, L3r, L3c} → J → L4. *Cuttable* steps: 6b, 13b, 17b, 17c, 19b, 20b, 21b, 21c, 22b. Each sits last in its lane, so a lane can stop before them and still return green.

## Steps
1. backend factory: dependencies and test path
   - files: `pyproject.toml`, `uv.lock` (changed)
   - layer: build · lane: 0
   - skills: none — project rules only
   - turns green: none
   - test first: `tests/test_contracts.py`, test_factory_importable: `import factory.ports, factory.gate.records, factory.agent_spec.models` succeeds
   - interfaces: produces deps `pipecat-boson==0.1.4`, `pydantic`, `anthropic`, `httpx` (after Glib's ADR answer); `[tool.pytest.ini_options] pythonpath = ["."]`
   - verify: `uv run pytest -m "not live" tests/test_contracts.py` → `passed`, and `uv run pytest -m "not live" tests/test_scaffold.py` → `4 passed`

2. backend factory: Agent Spec schema and validation
   - files: `factory/agent_spec/models.py`, `factory/agent_spec/validation.py` (new)
   - layer: domain · lane: 0
   - skills: none — project rules only
   - turns green: AC-6, AC-7
   - test first: `tests/test_agent_spec_schema.py`, test_recording_path_must_stay_in_recordings_dir: `"../x.wav"` and any recording on `source.kind == "brief"` → issue on that field
   - interfaces: produces pydantic models (all `extra="forbid"`): `AgentSpec(id, schema_version: Literal[1], source: TemplateSource | BriefSource, role, instructions, voice, output_modality: Literal["audio"], temperature: float | None, max_output_tokens: int | None, tools: list[ClientTool | ServerWebSearch], turn_detection: ServerVad | None, scenarios: list[Scenario], budget: BudgetLimits)`; `TemplateSource(kind="template", template_id: Literal["health-insurance","fraud-detection","customer-support","ai-receptionist","specialist-training"])`; `BriefSource(kind="brief", text: str)`; `ClientTool(kind="client", name, description, parameters: dict, mock: MockBehaviour)` with `MockBehaviour(default_output: str, by_argument: list[ArgCase])` and `ArgCase(when: dict[str, Any], output: str)`; `ServerWebSearch(kind="server", name="web_search")`; `ServerVad(threshold, prefix_padding_ms, silence_duration_ms)`; `Scenario(id, title, user_voice: Literal["chloe","eleanor","jake","marcus","nora","oliver"], user_turns: list[UserTurn] (min 1), expected_tool_call: ExpectedCall | None, rubric: Rubric)`; `UserTurn(text, recording: str | None, interrupt_after_assistant_ms: int | None)`; `Rubric(pass_criteria, partial_criteria, fail_criteria)`; `BudgetLimits(max_scenarios: int, max_audio_s_per_run: float, max_judge_calls_per_scenario: int, max_live_session_s: float)`; `SpecIssue(field: str, message: str)`; `validate_agent_spec(raw: Mapping[str, Any]) -> AgentSpec | list[SpecIssue]` (field = dotted pydantic `loc`; for a client tool without mock the field is `tools.<name>.mock`)
   - verify: `uv run pytest -m "not live" tests/test_agent_spec_schema.py` → all passed, failing run recorded first

3. backend factory: ports, domain events, run records, Eval Card model, doubles, fake server
   - files: `factory/ports.py`, `factory/gate/records.py`, `tests/doubles.py`, `tests/fake_realtime_server.py`, `tests/conftest.py` (new)
   - layer: ports / domain / test fixtures · lane: 0
   - skills: none — project rules only
   - turns green: none
   - test first: `tests/test_contracts.py`, test_fake_server_records_and_closes: a scripted `close(4429)` is seen by a plain `websockets` client with code 4429; received client events are timestamped
   - interfaces: produces in `factory/ports.py`: frozen dataclasses `Usage(input_tokens:int, cached_tokens:int, output_tokens:int)`, `AudioDelta(response_id:str, nbytes:int, t:float)`, `TranscriptDelta(response_id:str, text:str, t:float)`, `ResponseDone(response_id:str, status:str, usage:Usage|None, t:float)`, `ToolCall(call_id:str, name:str, arguments:dict, executor:Literal["client","server"], t:float)`, `SpeechStarted(t)`, `SpeechStopped(t)`, `SessionEnded(cause:Literal["quota refused","idle timeout","concurrency limit","closed"], close_code:int|None, error_text:str|None, t:float)`, `OtherEvent(type:str, t:float)`, `SessionEvent = Union[...]`; `class SessionRefused(Exception): error_text: str`; Protocols `RealtimeSession` (`async open(spec: AgentSpec) -> None` raises SessionRefused; `async send_audio(pcm: bytes) -> float` returns monotonic send time; `async send_tool_output(call_id: str, output: str) -> None`; `events() -> AsyncIterator[SessionEvent]`; `async close() -> None`), `SessionFactory = Callable[[], RealtimeSession]`, `TtsPort.synthesise(text: str, voice: str) -> bytes` (24 kHz s16le mono, raises `TtsError`), `JudgePort.judge(request: JudgeRequest) -> str`, `JudgeRequest(rubric: Rubric, user_turns: list[str], transcript: str, tool_calls: list[ToolCall])`, `BriefModel.draft_spec(brief: str) -> str`, `CardStorePort.save(card: EvalCard) -> Path`, `.latest(agent_id: str) -> EvalCard | None`; `Clock = Callable[[], float]` (default `time.monotonic`). In `factory/gate/records.py`: `Label = Literal["PASS","PARTIAL","FAIL"]`, `Cause = Literal["quota refused","idle timeout","concurrency limit","budget reached","judge reply invalid","audio missing"]`, `Judgment(label, rationale, evidence)`, `TurnRecord(scenario_id, turn_index, kind: Literal["scripted","live"], ttfa_ms: float|None, bargein_ms: float|None, bargein_status: Literal["measured","not measured"]|None)`, `ScenarioRecord(scenario_id, title, rubric, judgment: Judgment|None, transcript: str, tool_calls: list[ToolCall], expected_call_match: Literal["matched","not matched"]|None, audio_source: Literal["synthesised","recorded"])`, `GateRunRecord(agent_id, run_id, ended_at: datetime, scenarios, turns, usages: list[Usage|None], input_audio_s: float, output_audio_s: float, cause: Cause|None, cause_detail: str|None)`, pydantic `EvalCard` with every field of the spec's Eval Card table plus `raw_turns: list[TurnRecord]`. In `tests/doubles.py`: `FakeSession(script: list[SessionEvent | Delay | Refuse])` (records sends with timestamps, `open_calls` counter), `FakeSessionFactory` (counts calls), `FakeTts(fail_texts: set[str])` (counts requests), `FakeJudge(replies: list[str])` (records requests), `FakeBriefModel(reply: str)` (counts calls), `make_spec(**overrides) -> dict` (minimal valid raw spec). In `tests/fake_realtime_server.py`: `async with fake_realtime_server(script) as (url, received)`, where script actions are `send(event_dict)`, `wait_for(client_event_type)`, `delay(ms)`, `close(code)`
   - verify: `uv run pytest -m "not live" tests/test_contracts.py` → all passed

6. backend factory: brief → Agent Spec generator service
   - files: `factory/agent_spec/generator.py` (new)
   - layer: service · lane: L1
   - skills: none — project rules only
   - turns green: AC-1, AC-2
   - test first: none beyond the red-first tests
   - interfaces: consumes `BriefModel`, `validate_agent_spec`, `SpecIssue`; produces `MAX_BRIEF_CHARS = 1000`, `class BriefTooLong(Exception)` (message states 1,000), `async generate_from_brief(brief: str, model: BriefModel) -> AgentSpec | list[SpecIssue]` (length check before any call; parses JSON; forces `source = BriefSource(text=brief)`)
   - verify: `uv run pytest -m "not live" tests/test_generator.py` → passed

6b. *cuttable, waits on the generator ADR*: backend factory: Anthropic `BriefModel` adapter
   - files: `factory/agent_spec/brief_anthropic.py` (new)
   - layer: adapter · lane: L1
   - skills: none — project rules only
   - turns green: none
   - test first: `tests/test_generator.py`, test_brief_wrapped_as_data: the prompt puts the brief inside a delimited block after the schema instructions (SDK client faked)
   - interfaces: produces `AnthropicBriefModel(client, model_id: str)` implementing `BriefModel`
   - verify: `uv run pytest -m "not live" tests/test_generator.py -k brief_wrapped` → passed

7. backend factory: templates (Specialist Training authored; four placeholders)
   - files: `factory/agent_spec/templates/__init__.py`, `factory/agent_spec/templates/specialist_training.json`, `factory/agent_spec/templates/recordings/.gitkeep` (new)
   - layer: domain data · lane: L1
   - skills: none — project rules only
   - turns green: AC-3 (Specialist Training case; other four `xfail(strict=True)`), AC-5
   - test first: `tests/test_templates.py`, test_specialist_training_fits_audio_budget: each scenario has 1–2 user turns of ≤ 200 characters, and `max_output_tokens` is set
   - interfaces: produces `TEMPLATE_IDS: tuple[str, ...]` (5 ids), `load_template(template_id: str) -> AgentSpec` (deterministic, no model call; raises `TemplateNotAvailable` for the four without card text). Content: voice `"default"`, server VAD with F8 defaults, no client tools (assumed default), 6 scenarios with ProactBench-shaped rubrics, one scenario with `interrupt_after_assistant_ms`, budget 6 / 240 s / 1 / 180 s. Instructions ask for answers of at most two sentences. Glib reviews the rubrics before step 24.
   - verify: `uv run pytest -m "not live" tests/test_templates.py` → passed (4 xfailed)

8. backend factory: spike, pipecat-boson driven against the fake server (timebox 30 min)
   - files: `factory/runtime/boson_session.py` (new)
   - layer: adapter · lane: L2
   - skills: none — project rules only
   - turns green: none
   - test first: `tests/test_runtime_session.py`, test_spike_one_turn: `open()` sends `session.update` (the fake replies `session.created`); one `send_audio` reaches the fake as `input_audio_buffer.append` with its send time; a scripted `response.output_audio.delta` comes out of `events()` as `AudioDelta` with receipt time
   - interfaces: produces `BosonRealtimeSession(url: str, api_key: str | None, clock: Clock = time.monotonic)` implementing `RealtimeSession`; built on a private subclass `_TappedService(BosonRealtimeLLMService)` that wraps `_dispatch_boson_server_event` (raw inbound, before stale filtering), `_ws_send` (timestamps outgoing appends) and `_mark_websocket_disconnected` (reads `self._websocket.close_code` before delegating). Spec mapping: `instructions`, `voice`, `output_modalities=["audio"]`, `temperature`, `max_output_tokens`, `tools`, `turn_detection` (None → manual, F24). Read pipecat's base API from the installed package in `.venv`, not from memory. If the test is not green within 30 min, stop and return `blocked` with what failed.
   - verify: `uv run pytest -m "not live" tests/test_runtime_session.py -k spike` → passed

9. backend factory: session end causes and refused config
   - files: `factory/runtime/boson_session.py` (changed)
   - layer: adapter · lane: L2
   - skills: none — project rules only
   - turns green: AC-14, AC-15, AC-16, AC-20 (adapter halves)
   - test first: none beyond the red-first tests
   - interfaces: produces the mapping: `error` with `type == "insufficient_quota"` or close 4429 → `SessionEnded("quota refused")` (F13); `session.idle_timeout` → `SessionEnded("idle timeout")` (F8); close 1013 → `SessionEnded("concurrency limit")` (F21); any other close → `SessionEnded("closed", code)`; `error` before `session.created` → `open()` raises `SessionRefused(error_text)` (F7, F14)
   - verify: `uv run pytest -m "not live" tests/test_runtime_session.py -k "ac14 or ac15 or ac16 or ac20"` → 4 passed

10. backend factory: tool calls on the wire
   - files: `factory/runtime/boson_session.py` (changed)
   - layer: adapter · lane: L2
   - skills: none — project rules only
   - turns green: AC-21, AC-22 (adapter halves)
   - test first: none beyond the red-first tests
   - interfaces: produces `ToolCall(executor="server")` for a `function_call` item with `executor: "server"` (F10), and the adapter sends nothing for it; `ToolCall(executor="client")` emitted once arguments are done; `send_tool_output` sends exactly one `conversation.item.create` with `function_call_output` (F3). pipecat's own function-call dispatch must not answer (no handler registered). Record in INSIGHTS whether pipecat also sends `response.create` (see Open questions).
   - verify: `uv run pytest -m "not live" tests/test_runtime_session.py -k "ac21 or ac22"` → 2 passed

11. backend factory: transcript, usage, speech events, unknown types
   - files: `factory/runtime/boson_session.py` (changed)
   - layer: adapter · lane: L2
   - skills: none — project rules only
   - turns green: none
   - test first: `tests/test_runtime_session.py`, test_usage_and_transcript_mapping: `response.output_audio_transcript.delta` → `TranscriptDelta` (F18); `response.done` with usage → `Usage(22, 0, 3)` from the smoke shape (F2); `usage: null` or a non-numeric count → `None`; `speech_started`/`speech_stopped` → events (F15); unknown type → `OtherEvent`
   - interfaces: as step 3
   - verify: `uv run pytest -m "not live" tests/test_runtime_session.py -k usage_and_transcript` → passed

12. backend factory: gate preflight
   - files: `factory/gate/runner.py` (new)
   - layer: service · lane: L3r
   - skills: none — project rules only
   - turns green: AC-4, AC-46
   - test first: none beyond the red-first tests
   - interfaces: consumes `validate_agent_spec`, `FakeSessionFactory`; produces `class GateRefused(Exception): reasons: list[str]` (AC-4: names each missing `budget.*` field; AC-46: message contains both counts, e.g. "7 scenarios exceed the limit of 6"), `preflight(raw: Mapping[str, Any]) -> AgentSpec`
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k "ac4 or ac46"` → 2 passed, session factory called 0 times

13. backend factory: TTS cache and audio source
   - files: `factory/gate/tts_cache.py`, `factory/gate/tts_boson.py` (new)
   - layer: service + adapter · lane: L3r
   - skills: none — project rules only
   - turns green: AC-8, AC-10
   - test first: `tests/test_tts_cache.py`, test_cache_key_is_text_and_voice: same text with another voice → a second request
   - interfaces: produces `TurnAudioSource(tts: TtsPort, cache_dir: Path, recordings_dir: Path)` with `async audio_for(turn: UserTurn, voice: str) -> tuple[bytes, Literal["synthesised","recorded"]]`, raising `AudioMissing(turn_label: str)` (label `"<scenario_id> turn <n>"`); cache file `<cache_dir>/<sha256(voice + "\0" + text)>.pcm`; `BosonTts(client: httpx.AsyncClient, api_key: str)` posts to `/v1/audio/speech` with `stream: true`, `response_format: "pcm"` (F22), no retry
   - verify: `uv run pytest -m "not live" tests/test_tts_cache.py -k ac8` and `uv run pytest -m "not live" tests/test_gate_runner.py -k ac10` → passed

13b. *cuttable*: recording fallback
   - files: `factory/gate/tts_cache.py` (changed)
   - layer: service · lane: L3r
   - skills: none — project rules only
   - turns green: AC-9
   - test first: none
   - interfaces: reads a WAV 24 kHz 16-bit mono recording with stdlib `wave`; a different format raises `AudioMissing`
   - verify: `uv run pytest -m "not live" tests/test_tts_cache.py -k ac9` → passed

14. backend factory: paced playback and TTFA
   - files: `factory/gate/playback.py` (new)
   - layer: service · lane: L3r
   - skills: none — project rules only
   - turns green: AC-47, AC-25
   - test first: `tests/test_playback.py`, test_chunks_stay_under_f4_limit: every append is ≤ 100 ms of audio (4,800 bytes)
   - interfaces: produces `CHUNK_MS = 100`, `async play_turn(session: RealtimeSession, pcm: bytes, *, sleep=asyncio.sleep) -> float` (returns the send time of the last speech chunk), `async stream_silence_until(session, stop: asyncio.Event, max_s: float) -> None`. TTFA = first `AudioDelta.t` of the next response − last speech chunk time. AC-25 runs against `fake_realtime_server` through `FakeSession`'s server-delay script.
   - verify: `uv run pytest -m "not live" tests/test_playback.py -k "ac47 or ac25"` → 2 passed

15. backend factory: judge request and reply parsing; Anthropic adapter
   - files: `factory/gate/judge.py`, `factory/gate/judge_anthropic.py` (new)
   - layer: service + adapter · lane: L3r
   - skills: none — project rules only
   - turns green: AC-11, AC-18 (call-count half)
   - test first: `tests/test_judge.py`, test_fenced_or_prose_reply_is_invalid
   - interfaces: produces `build_judge_prompt(req: JudgeRequest) -> str` (transcript and turns in delimited data blocks, instructions say they are data); `parse_judgment(raw: str) -> Judgment | None` (strict JSON object with exactly `label` ∈ {PASS, PARTIAL, FAIL}, non-empty `rationale`, non-empty `evidence`); `async judge_scenario(judge: JudgePort, req: JudgeRequest) -> Judgment | None` (exactly one call); `AnthropicJudge(client: anthropic.AsyncAnthropic, model_id: str)` with `max_retries=0`
   - verify: `uv run pytest -m "not live" tests/test_judge.py` → passed

16. backend factory: gate run loop
   - files: `factory/gate/runner.py` (changed)
   - layer: service · lane: L3r
   - skills: none — project rules only
   - turns green: AC-14, AC-15, AC-16, AC-17, AC-20, AC-22, AC-24 (runner halves)
   - test first: `tests/test_gate_runner.py`, test_one_judge_call_per_scenario_budget: budget `max_judge_calls_per_scenario` is never exceeded
   - interfaces: produces `async run_gate(spec: AgentSpec, *, sessions: SessionFactory, audio: TurnAudioSource, judge: JudgePort, clock: Clock = time.monotonic) -> GateRunRecord`. One session per scenario (AC-55): each scenario opens its own session from `sessions()`, runs its turns, then closes it. A late response after the scenario ends is dropped with that session. A single run-wide `_Meter` sums input and output bytes across all scenario sessions against `budget.max_audio_s_per_run` (AC-56). A refused session raises `GateAborted(error_text)` and leaves no record (AC-20). *(Replaced 2026-10-24: was "One session per gate run"; see steps 16c–16i.)* `SessionEnded` cause → record `cause` and stop. `SessionRefused` → raise `GateAborted(error_text)` with no record. Input seconds = appended bytes / 48,000, output seconds = delta bytes / 48,000 (24 kHz s16le, F4); when input + output reaches `budget.max_audio_s_per_run` → cause "budget reached". A client `ToolCall` → `send_tool_output(call_id, select_mock(tool, args))`. `OtherEvent` is ignored. An invalid judgment → cause "judge reply invalid". `AudioMissing` → cause "audio missing", `cause_detail` = turn label. `select_mock(tool: ClientTool, arguments: dict) -> str` (first `ArgCase` whose `when` is a subset of the arguments, else `default_output`).
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py` → passed

16c. backend factory: response-start event and per-session test doubles *(delta 2026-10-24, AC-55…AC-61, after live gate run `20261024T161045Z-d663176a`)*
   - files: `factory/ports.py`, `factory/runtime/boson_session.py`, `tests/doubles.py`, `tests/fake_realtime_server.py`, `tests/test_runtime_session.py`, `tests/test_contracts.py` (changed)
   - layer: ports / adapter / test fixtures
   - skills: none — project rules only
   - turns green: none
   - test first: `tests/test_runtime_session.py`, test_response_created_maps_to_event: the fake server sends `response.created` with `response.id = "r1"`; `events()` yields `ResponseCreated("r1", t)` (F17), not `OtherEvent`. Also `tests/test_contracts.py`, test_fake_server_scripts_per_connection: with `scripts=[[…a…], […b…]]`, the first connection gets script a, the second gets script b, and each `Received` carries its `conn` index.
   - interfaces: produces `@dataclass(frozen=True) class ResponseCreated(response_id: str, t: float)`, added to the `SessionEvent` union. `BosonRealtimeSession` maps `response.created` to it, with an `# F17` comment. `FakeSessionFactory(script=None, clock=…, *, scripts: list[list[SessionEvent | Delay | Refuse]] | None = None, restamp: bool = False)`: call k gets `scripts[k]`, and the old `script` still works for every call. `FakeSession(..., restamp: bool = False)`: when True, each yielded event is `dataclasses.replace(event, t=clock())`, so window timing in tests uses real time. `fake_realtime_server(script=None, *, scripts=None, auto_ack=True)`: `Received(event, t, conn: int)`.
   - verify: `uv run pytest -m "not live" tests/test_runtime_session.py -k response_created` → 1 passed; `uv run pytest -m "not live" tests/test_contracts.py` → all passed

16d. backend factory: one session per scenario, budget summed across sessions
   - files: `factory/gate/runner.py`, `tests/test_gate_runner.py` (changed)
   - layer: service
   - skills: none — project rules only
   - turns green: AC-55, AC-56
   - test first: none beyond the red-first tests. Red-first: `tests/test_gate_runner.py`, test_ac55_one_session_per_scenario: three scenarios with distinct TTS PCM per text (a `FakeTts` subclass in the test returns bytes derived from the text) and `FakeSessionFactory(scripts=[s1, s2, s3])`. Expect `factory.calls == 3`, every session `closed`, each session's audio sends to hold only its own scenario's speech bytes (plus silence), and each `FakeJudge` request transcript to hold only its own session's transcript text. Then test_ac56_budget_sums_across_sessions: limit 10 s, three scenarios of about 4 s of input audio each (TTS PCM 4.0 s, no-op `sleep`, `QUIET_WINDOW_S` set to 0.05); expect `cause == "budget reached"` with 2 complete scenario records and the stop inside the third (`factory.calls == 3`). Update `test_happy_path_records_scenario_ttfa_usage_and_audio` line 177 from `calls == 1` to `calls == len(spec.scenarios)`. This follows the spec change (AC-55), not the code.
   - interfaces: produces `class _Meter(limit_s: float)` with `input_bytes`, `output_bytes`, `over_budget() -> bool`, created once per run. `_MeteredSession(session, meter: _Meter, wake: asyncio.Queue)` counts into the shared meter. `_Run` keeps the run-wide lists (`scenarios`, `turns`, `usages`, `cause`) and the meter. A new `_ScenarioSession` holds what lives for one scenario: `queue`, `carry`, `_pump_task`, the metered session, plus `async open(spec)` and `async shutdown()`. `_Run._scenario(scenario)` opens a `_ScenarioSession` from `sessions()`, runs the turns, and shuts it down in `finally`. `run_gate` signature unchanged. `record()` reads input and output seconds from the meter.
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k "ac55 or ac56"` → 2 passed, failing run recorded first

16e. backend factory: 2 s quiet window ends a turn, responses joined, window silence counted
   - files: `factory/gate/runner.py`, `tests/test_gate_runner.py` (changed)
   - layer: service
   - skills: none — project rules only
   - turns green: AC-57, AC-58, AC-60
   - test first: `tests/test_gate_runner.py`, test_quiet_window_default_is_two_seconds: `runner.QUIET_WINDOW_S == 2.0`. Add an autouse fixture in `tests/test_gate_runner.py`, `_short_quiet_window(monkeypatch)`, that sets `runner.QUIET_WINDOW_S = 0.05` for every test not marked `@pytest.mark.real_window`. Register that marker in `tests/conftest.py` with `config.addinivalue_line` (the project's `--strict-markers`). The AC-57, AC-58 and AC-60 tests use the real 2.0 s. Red-first:
     - test_ac57_turn_ends_two_seconds_after_last_response (`restamp=True`): A created, delta, done; Delay 1.2; B created, delta, done. Expect the first audio send of the next scripted turn ≥ B's `done.t` + 2.0 − 0.1, and not within 2 s of A's done.
     - test_ac58_split_reply_joined_for_its_own_scenario_only: two scenarios. st-5's session script has transcript "No problem." in response A, then Delay 1.0, then "Acknowledge their feeling first, then say what you will fix." in response B. st-6 has its own script. Expect st-5's judge request transcript to contain both texts in that order, and st-6's request to contain neither.
     - test_ac60_window_silence_counts_toward_budget: one turn of 1.0 s of speech, real 2 s window. Expect `record.input_audio_s >= 1.0 + 2.0 - 0.15`.
   - interfaces: produces `QUIET_WINDOW_S: float = 2.0` (module constant, read at call time so tests can shrink it) and `_ScenarioSession.next_event(timeout: float | None = None) -> SessionEvent | None` (None on timeout; carry is drained first).

     New `_read_reply` loop:
     - A response counts as started at `ResponseCreated` or at the first event that carries an unseen `response_id`, whichever comes first. Its `response_id` is appended to `reply.response_ids` in start order.
     - On a `ResponseDone` that ends reading, the loop no longer breaks. It runs a quiet window: it starts `stream_silence_until(session, window_stop, max_s=QUIET_WINDOW_S)` and waits on `next_event(timeout=remaining)`. If a new response starts before the window ends, it stops the silence and goes back to reading; the window restarts at that response's done. If the window elapses, the turn ends. Any non-start event inside the window is handled as before (tool calls, usage), and the window keeps running.
     - The reply text is `" ".join(text of each response in start order)`, where one response's text is its concatenated transcript deltas (F18).
     - A pending client-tool follow-up still waits without a timeout, as now, and its response counts toward `responses`.
     - No quiet window on a turn whose reply was interrupted: that reply ends at the interrupted response's `ResponseDone`, as now (AC-28 path unchanged).
     - The run-wide meter counts window silence like any other input (AC-60), and `_BudgetReached` can fire inside the window.
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k "ac57 or ac58 or ac60 or quiet_window"` → 4 passed, failing run recorded first

16f. backend factory: TTFA on the first response only
   - files: `factory/gate/runner.py`, `tests/test_gate_runner.py` (changed)
   - layer: service
   - skills: none — project rules only
   - turns green: AC-59
   - test first: none beyond the red-first test. Red-first: `tests/test_gate_runner.py`, test_ac59_ttfa_on_first_response_only (`restamp=True`, real window): one turn, then Delay 0.4, delta of response A, done A, then Delay 1.2, delta of response B, done B. Expect exactly one `TurnRecord` for the turn, with `ttfa_ms` 400 ± 50. If it passes on the first run (the current code already takes the first delta), record that run as the evidence and say so in the implementer report. Do not weaken the assertion to force a red run.
   - interfaces: `reply.ttfa_ms` is set only from the first `AudioDelta` whose `response_id == reply.response_ids[0]`
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k ac59` → 1 passed

16g. backend factory: responses per turn in the record and on the card
   - files: `factory/gate/records.py`, `factory/gate/runner.py`, `factory/gate/render.py`, `tests/test_gate_runner.py`, `tests/test_card_store.py` (changed)
   - layer: domain / service
   - skills: none — project rules only
   - turns green: AC-61
   - test first: none beyond the red-first test. Red-first: `tests/test_gate_runner.py`, test_ac61_responses_per_turn_recorded_and_shown: one scenario with a split turn (two responses inside the window) and one normal turn. Expect `record.turns[*].responses == [2, 1]`; `build_card(record)` keeps them in `raw_turns`; `render_card_text(card)` contains `responses per turn` and both counts with their scenario id and turn number. Also `tests/test_card_store.py`, test_card_roundtrip_keeps_responses: save, then `latest()`, keeps `responses == 2`.
   - interfaces: `TurnRecord` gains a last field, `responses: int = 1` (the default keeps existing constructors and stored cards valid). The runner writes `len(reply.response_ids)` into it. `render_card_text` adds one line, `Responses per turn: <scenario_id> turn <n> = <count>, …`, with counts above 1 marked `(split)`. `EvalCard` and `build_card` are unchanged; the field travels through `raw_turns`.
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k ac61` → 1 passed; `uv run pytest -m "not live" tests/test_card_store.py` → all passed

16h. backend factory: st-5 template rewording (no internal pause, rubric unchanged)
   - files: `factory/agent_spec/templates/specialist_training.json`, `tests/test_templates.py` (changed)
   - layer: domain data
   - skills: none — project rules only
   - turns green: none (fixes the live defect's trigger; the AC-57/58 guards cover the general case)
   - test first: `tests/test_templates.py`, test_no_scripted_turn_has_an_internal_sentence_break: for every Specialist Training user turn, `re.search(r"[.?!…](?=.)", text.strip()) is None`, meaning no sentence end before the final character. Also test_st5_rubric_unchanged: st-5's `rubric` equals the dict in the current file (hard-coded in the test before the edit).
   - interfaces: st-5 turn 2 text becomes one sentence with no internal stop, for example `"Which comes first with an angry customer, the apology or the fix?"`. `interrupt_after_assistant_ms` stays 1500. Rubric, voice and the other turns are unchanged. The TTS cache key changes, so the next live run makes one new TTS 3 request for this turn (F22).
   - verify: `uv run pytest -m "not live" tests/test_templates.py` → all passed (the 4 xfailed placeholder templates are unchanged)

16i. backend factory: wire confirmation with several sessions
   - files: `tests/test_gate_wire.py` (changed)
   - layer: test
   - skills: none — project rules only
   - turns green: none (wire-level confirmation of AC-55 through the real adapter)
   - test first: `tests/test_gate_wire.py`, test_wire_one_connection_per_scenario: a two-scenario spec against `fake_realtime_server(scripts=[a, b])` with `QUIET_WINDOW_S` monkeypatched to 0.05. Expect two connections (`conn` 0 and 1), each with its own `session.update`, and the stored card has 2 scenarios.
   - interfaces: consumes 16c to 16g
   - verify: `uv run pytest -m "not live" tests/test_gate_wire.py` → all passed
   - checks after 16i (single-agent fix mode): `uv run pytest -m "not live"` · `uv run ruff check` · `uv run ruff format --check`. Then the main session reruns the live gate and checks st-5 turn 2 shows `responses = 1` and no st-5 text appears in st-6.

16j. backend factory: keep the invalid judge reply, capped *(delta 2026-10-24, AC-62…AC-64 and the F27 rubric rule)*
   - files: `factory/gate/judge.py`, `tests/test_judge.py` (changed)
   - layer: service
   - skills: none — project rules only
   - turns green: AC-63
   - test first: none beyond the red-first test. Red-first: `tests/test_judge.py`, test_ac63_long_invalid_reply_capped_and_flagged. The judge double returns `"x" * 5000`. Expect `outcome.judgment is None`, `outcome.raw_reply == "x" * 2000` (exactly the first 2,000 characters), `outcome.raw_truncated is True`, and exactly one judge call. Also test_valid_reply_keeps_no_raw: a valid reply gives `raw_reply is None` and `raw_truncated is False`.
   - interfaces: produces `RAW_REPLY_MAX_CHARS = 2000`, `@dataclass(frozen=True) class JudgeOutcome(judgment: Judgment | None, raw_reply: str | None, raw_truncated: bool)`, and `async judge_scenario_outcome(judge: JudgePort, req: JudgeRequest) -> JudgeOutcome`. It makes exactly one call. On an invalid parse it keeps `raw[:RAW_REPLY_MAX_CHARS]` and sets `raw_truncated = len(raw) > RAW_REPLY_MAX_CHARS`. The kept text is never parsed again and never used as rationale or evidence. `judge_scenario(judge, req) -> Judgment | None` stays as a wrapper that returns `(await judge_scenario_outcome(...)).judgment`, so the existing `tests/test_judge.py` callers stay unchanged.
   - verify: `uv run pytest -m "not live" tests/test_judge.py -k "ac63 or keeps_no_raw"` → 2 passed, failing run recorded first; then `uv run pytest -m "not live" tests/test_judge.py` → all passed

16k. backend factory: diagnostics in the run record and the stored card
   - files: `factory/gate/records.py`, `factory/gate/runner.py`, `tests/test_gate_runner.py`, `tests/test_card_store.py` (changed)
   - layer: domain / service
   - skills: none — project rules only
   - turns green: AC-62
   - test first: none beyond the red-first tests. Red-first:
     - `tests/test_gate_runner.py`, test_ac62_invalid_reply_and_transcript_length_in_record: the judge double returns `{"label": "MAYBE"}`, and the scenario's session script yields transcript text whose joined transcript is exactly 412 characters. Build the text as `"a" * 412` in one response, with the window shrunk as in the existing fixture. Expect `record.cause == "judge reply invalid"`, `record.scenarios[0].judge_raw_reply == '{"label": "MAYBE"}'`, `judge_raw_truncated is False` and `transcript_chars == 412`.
     - `tests/test_card_store.py`, test_ac62_diagnostics_survive_store_roundtrip: `build_card(record)`, then `FileCardStore.save`, then `latest()`. The loaded card's `scenarios[0]` has the same three values.
     - `tests/test_card_store.py`, test_card_without_diagnostics_still_loads: a stored card JSON written without the three keys (copy the shape of a pre-16k card) loads, with `judge_raw_reply is None`, `judge_raw_truncated is False` and `transcript_chars is None`.
   - interfaces: `ScenarioRecord` gains three last fields, all defaulted: `judge_raw_reply: str | None = None`, `judge_raw_truncated: bool = False`, `transcript_chars: int | None = None`. The runner calls `judge_scenario_outcome` and, only when `outcome.judgment is None`, fills `judge_raw_reply=outcome.raw_reply`, `judge_raw_truncated=outcome.raw_truncated` and `transcript_chars=len(request.transcript)`. The rest of the code path stays the same: one judge call, cause "judge reply invalid", `cause_detail = scenario.id`. `EvalCard` and `build_card` are unchanged, because the fields travel through `EvalCard.scenarios`.
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k ac62` → 1 passed; `uv run pytest -m "not live" tests/test_card_store.py` → all passed, failing runs recorded first

16l. backend factory: rendered card shows the cause, the length and a "kept" note, never the reply
   - files: `factory/gate/render.py`, `tests/test_card_store.py` (changed)
   - layer: domain
   - skills: none — project rules only
   - turns green: AC-64
   - test first: none beyond the red-first test. Red-first: `tests/test_card_store.py`, test_ac64_render_hides_raw_reply. Build a card from a record whose scenario st-1 has `judgment=None`, `judge_raw_reply='<b>PASS</b> {"label":"PASS","rationale":"r-secret","evidence":"e-secret"}'`, `judge_raw_truncated=True`, `transcript_chars=412`, and cause "judge reply invalid". Expect `render_card_text(card)` to contain `st-1`, `judge reply invalid`, `412` and `raw reply kept`, and to contain none of `<b>`, `r-secret`, `e-secret` or the full raw string. Also assert that `card.failing_rubric_lines` holds no entry for st-1, so nothing from the reply appears as rationale or evidence.
   - interfaces: `render_card_text` adds one line per scenario with `judgment is None and transcript_chars is not None`, of the form `Scenario <id>: judge reply invalid; transcript <n> chars; raw reply kept (not shown)`, with ` (truncated)` appended when `judge_raw_truncated`. The line never reads `judge_raw_reply`.
   - verify: `uv run pytest -m "not live" tests/test_card_store.py -k ac64` → 1 passed, failing run recorded first

16m. backend factory: st-5 rubric drops the criteria the judge cannot decide (F27)
   - files: `factory/agent_spec/templates/specialist_training.json`, `tests/test_templates.py` (changed)
   - layer: domain data
   - skills: none — project rules only
   - turns green: none. This is the spec's Scenario-contract rule: a criterion must be decidable from what the judge receives (F27).
   - test first: `tests/test_templates.py`, test_no_criterion_asks_judge_to_see_a_cut_off. For every Specialist Training scenario, no pass, partial or fail criterion matches `re.compile(r"cut off|mid-sentence|ends early|stops its first answer|continues to its end", re.I)`. This test fails before the edit, on st-5. Update `_ST5_RUBRIC` in `tests/test_templates.py` to the new rubric: remove exactly the pass criterion "The assistant stops its first answer when interrupted, so the first answer in the transcript ends early or mid-sentence." and the partial criterion "The answer to the second question is correct, but the first answer continues to its end as if there was no interruption." Keep every other criterion in its order. Keep the `interrupt_after_assistant_ms == 1500` assertion. This expected-value change follows the spec change (Scenario rubric rule, F27), not the code.
   - interfaces: st-5 in `specialist_training.json` loses exactly those two strings. Turn texts, voice, `interrupt_after_assistant_ms`, the fail criteria and every other scenario stay unchanged. Interruption handling is shown on the card by barge-in stop time (informational, AC-19).
   - verify: `uv run pytest -m "not live" tests/test_templates.py` → all passed (the 4 xfailed placeholder templates are unchanged), with the failing run of `-k cut_off` recorded first
   - checks after 16m: `uv run pytest -m "not live"` · `uv run ruff check` · `uv run ruff format --check`. Then the main session reruns the live gate once.

17b. *cuttable*: expected tool call match
   - files: `factory/gate/runner.py` (changed)
   - layer: service · lane: L3r
   - turns green: AC-23
   - skills: none — project rules only
   - test first: none
   - interfaces: `expected_call_match(expected: ExpectedCall, calls: list[ToolCall]) -> Literal["matched","not matched"]` (name equal, declared args a subset); does not change the label (AC-19)
   - verify: `uv run pytest -m "not live" tests/test_gate_runner.py -k ac23` → passed

17c. *cuttable*: interrupting turns and barge-in timing
   - files: `factory/gate/playback.py`, `factory/gate/runner.py` (changed)
   - layer: service · lane: L3r
   - skills: none — project rules only
   - turns green: AC-28
   - test first: none
   - interfaces: an interrupt turn starts after `interrupt_after_assistant_ms` of received assistant audio; the mark is the send time of its first chunk; the end is the last `AudioDelta.t` with the interrupted `response_id` before its `ResponseDone`; writes `TurnRecord.bargein_ms` and `bargein_status`
   - verify: `uv run pytest -m "not live" tests/test_playback.py -k ac28` → passed

18. backend factory: verdict
   - files: `factory/gate/verdict.py` (new)
   - layer: domain · lane: L3c
   - skills: none — project rules only
   - turns green: AC-12, AC-13, AC-18 (verdict half), AC-19
   - test first: none beyond the red-first tests
   - interfaces: produces `decide_verdict(record: GateRunRecord) -> tuple[Literal["released","rejected","incomplete"], list[FailingLine]]`; `FailingLine(scenario_id, label, criteria: Rubric, rationale, evidence)`; `cause` set → incomplete; any non-PASS → rejected; else released. Takes no metrics argument.
   - verify: `uv run pytest -m "not live" tests/test_verdict.py` → passed

19. backend factory: TTFA metrics
   - files: `factory/gate/metrics.py` (new)
   - layer: domain · lane: L3c
   - skills: none — project rules only
   - turns green: AC-27
   - test first: `tests/test_metrics.py`, test_percentile_method: nearest-rank percentile on a known 20-value list (the method is named in the docstring)
   - interfaces: produces `TTFA_LABEL` (states timing starts at the last user speech chunk sent and includes the server VAD silence window, F8), `ttfa_summary(turns: list[TurnRecord]) -> TtfaSummary(p50_ms, p95_ms, n, label)`
   - verify: `uv run pytest -m "not live" tests/test_metrics.py -k ac27` → passed

19b. *cuttable*: scripted-only filter — turns green AC-48; `ttfa_summary` keeps only `kind == "scripted"`; lane L3c; files `factory/gate/metrics.py`; skills: none — project rules only; verify `uv run pytest -m "not live" tests/test_metrics.py -k ac48` → passed

20b. *cuttable; answered by Glib 2026-10-24: p50 + max with N (spec AC-54)*: barge-in aggregate — turns green AC-29 and AC-54; `bargein_summary(turns) -> BargeinSummary(p50_ms, max_ms, n)` excluding "not measured" turns (verify example from AC-54: 200, 300, 900 ms plus one "not measured" → p50 300, max 900, N 3); lane L3c; files `factory/gate/metrics.py`; skills: none — project rules only; verify `uv run pytest -m "not live" tests/test_metrics.py -k "ac29 or ac54"` → passed

21. backend factory: cost
   - files: `factory/gate/cost.py`, `factory/gate/render.py` (new)
   - layer: domain · lane: L3c
   - skills: none — project rules only
   - turns green: AC-30, AC-31, AC-32 (card half)
   - test first: `tests/test_cost.py`, test_non_numeric_usage_counts_as_missing
   - interfaces: produces F12 constants (`AUDIO_IN_USD_PER_MIN = 0.0023`, `AUDIO_OUT_USD_PER_MIN = 0.014`, `INPUT_USD_PER_M = 0.75`, `CACHED_USD_PER_M = 0.25`, `OUTPUT_USD_PER_M = 4.50`, each with an `# F12` comment), `AUDIO_COST_LABEL = "estimated from Boson's published per-minute rates"`, `TOKEN_NOT_MEASURABLE = "Billed token cost: not measurable, the API returns no usage (F2)"`, `audio_cost(input_min: float, output_min: float) -> AudioCost`, `token_cost(usages: list[Usage | None]) -> TokenCost | Literal["not measurable"]`, `render_card_text(card: EvalCard) -> str` (verdict as a word; no amount next to "billed", "actual" or "invoiced")
   - verify: `uv run pytest -m "not live" tests/test_cost.py -k "ac30 or ac31 or ac32"` → 3 passed

21b. *cuttable, waits on answer (cached counting)*: measured token cost — turns green AC-50; lane L3c; files `factory/gate/cost.py`; skills: none — project rules only; `TOKEN_COST_LABEL = "measured from reported usage × Boson's published token rates"`; `INPUT_TOKENS_INCLUDE_CACHED: bool` set from Glib's answer; verify `uv run pytest -m "not live" tests/test_cost.py -k ac50` → passed

21c. *cuttable, after 21b*: token headline — turns green AC-51; lane L3c; files `factory/gate/render.py`; skills: none — project rules only; verify `uv run pytest -m "not live" tests/test_cost.py -k ac51` → passed

22. backend factory: card builder and store
   - files: `factory/gate/card_builder.py`, `factory/gate/card_store.py` (new)
   - layer: domain + adapter · lane: L3c
   - skills: none — project rules only
   - turns green: AC-33
   - test first: `tests/test_card_store.py`, test_same_second_runs_distinct_ids
   - interfaces: produces `build_card(record: GateRunRecord, ihbench: IhbenchResult | None = None) -> EvalCard` (RQ "not available" when None), `FileCardStore(root: Path)` implementing `CardStorePort` at `<root>/<agent_id>/<run_id>.json`, opened with mode `"x"`; `new_run_id(now: datetime) -> str` (`YYYYmmddTHHMMSSZ-<8 hex>`)
   - verify: `uv run pytest -m "not live" tests/test_card_store.py -k "ac33 or same_second"` → 2 passed

22b. *cuttable, waits on Spec B format*: IHBench RQ — turns green AC-34; lane L3c; files `factory/gate/ihbench.py`; skills: none — project rules only; `load_ihbench_result(path: Path) -> IhbenchResult | None` (unreadable → None); verify `uv run pytest -m "not live" tests/test_card_store.py -k ac34` → passed

23. backend factory: composition root and CLI
   - files: `factory/composition.py`, `factory/__main__.py`, `tests/test_gate_wire.py` (new)
   - layer: composition / entry · lane: J
   - skills: none — project rules only
   - turns green: none (wire confirmation of AC-14, AC-16, AC-25, AC-47 through the real adapter + runner)
   - test first: `tests/test_gate_wire.py`, test_wire_quota_refused_card_incomplete: real `BosonRealtimeSession` + `run_gate` + `build_card` against `fake_realtime_server` closing with 4429 → stored card `incomplete`, "quota refused"
   - interfaces: consumes everything above; produces `build_app(env: Mapping[str, str], results_dir: Path) -> FactoryApp` (reads `BOSON_API_KEY`, `ANTHROPIC_API_KEY`, `FACTORY_JUDGE_MODEL`; missing → `ConfigError` naming the variable, never its value), `async FactoryApp.run_gate_for_template(template_id: str) -> EvalCard | GateAborted`; CLI `python -m factory gate --template specialist-training` prints `render_card_text` and the stored path
   - verify: `uv run pytest -m "not live" tests/test_gate_wire.py` → passed

24. backend factory: live end-to-end gate (main session runs it)
   - files: `tests/test_e2e_gate.py` (new)
   - layer: test · lane: J
   - skills: none — project rules only
   - turns green: AC-45 (run by the main session, not the lane)
   - test first: `tests/test_e2e_gate.py`, test_ac45_specialist_training_live (`@pytest.mark.live`): stored card has a verdict, `ttfa.n >= 1`, input and output minutes > 0, and an estimated audio cost
   - interfaces: consumes `build_app`
   - verify (lane): `uv run pytest -m "not live" tests/test_e2e_gate.py` → `deselected` (collected cleanly); verify (main session): `uv run pytest -m live tests/test_e2e_gate.py` → `1 passed`

25. *P2, cuttable* backend factory: web dependencies
   - files: `pyproject.toml`, `uv.lock` (changed)
   - layer: build · lane: L4
   - skills: none — project rules only
   - turns green: none
   - test first: none
   - interfaces: `uv add fastapi uvicorn` after ADR sign-off
   - verify: `uv run pytest -m "not live" tests/test_contracts.py` → passed

26. *P2, cuttable* backend factory: live session service
   - files: `factory/live/__init__.py`, `factory/live/session.py` (new)
   - layer: service · lane: L4
   - skills: none — project rules only
   - turns green: AC-26, AC-35
   - test first: none beyond the red-first tests
   - interfaces: produces `async run_live(spec: AgentSpec, session: RealtimeSession, mic: AsyncIterator[bytes], out: LiveSink, clock) -> LiveEnd`, with `LiveSink` methods `audio(pcm)`, `stop_playback(response_id)`, `ttfa(ms, label)`, `ended(reason: Literal["limit reached","inactivity","quota refused","closed"])`; `LIVE_TTFA_LABEL` names `speech_stopped` as the start; the limit is `budget.max_live_session_s`
   - verify: `uv run pytest -m "not live" tests/test_live_session.py` → passed

27. *P2, cuttable* web factory: demo server
   - files: `factory/web/__init__.py`, `factory/web/app.py` (new)
   - layer: entry · lane: L4
   - skills: none — project rules only
   - turns green: AC-32 (page half), AC-37, AC-43, AC-44, AC-53
   - test first: `tests/test_web.py`, test_error_text_escaped
   - interfaces: `create_web_app(factory_app: FactoryApp) -> FastAPI`; `GET /` static page; `GET /api/templates`; `GET /api/agents/{template_id}/spec`; `GET /api/agents/{agent_id}/card/latest`; `POST /api/agents/{agent_id}/scenarios/{scenario_id}/check` (single-scenario check; result marked "single-scenario check"; never writes the stored card's verdict); `WS /ws/live/{agent_id}` (browser ↔ server PCM; keys stay server-side; on 4429 sends `{"type":"ended","reason":"quota refused"}` and the client does not reconnect)
   - verify: `uv run pytest -m "not live" tests/test_web.py` → passed

28. *P2, cuttable* web factory: demo page
   - files: `factory/web/static/index.html` (new)
   - layer: entry (UI) · lane: L4
   - skills: none — project rules only
   - turns green: none (browser ACs are checked by the main session)
   - test first: none
   - interfaces: one page with five template cards (AC-38), the spec view on click (AC-49), the stored latest card with run id and timestamp (AC-52), scenario progress (AC-39), the verdict as a word (AC-40), live TTFA with its start-point label (AC-41), playback stopped on `speech_started` (AC-42), a "not released" banner whenever the latest verdict ≠ released (AC-36); text inserted with `textContent` only
   - verify: `uv run pytest -m "not live" tests/test_web.py -k "ac37"` → passed (the page asset contains no key)

## Contracts & data
- Agent Spec pydantic models, `validate_agent_spec`: `factory/agent_spec/models.py`, `validation.py` (lane 0; single source).
- Ports and domain events: `factory/ports.py` (lane 0). Run records and the `EvalCard` model: `factory/gate/records.py` (lane 0).
- F12 rates: `factory/gate/cost.py` only, each with an `# F12` comment.
- Stored data (git-ignored `results/`): `results/cards/<agent_id>/<run_id>.json`, `results/tts-cache/<sha256>.pcm`.
- Template data: `factory/agent_spec/templates/specialist_training.json`; recordings in `factory/agent_spec/templates/recordings/`.
- Env: `FACTORY_JUDGE_MODEL` is new. Main-session edit: add it to `.env.example` (lane J does not own that file).
- No migrations, no mirrors, no message catalog.

## Checks for the implementer
- multi-agent, per lane: `uv run pytest -m "not live" tests/test_<area>.py` for each test file the lane owns (with `-k ac<N>` where a step says so) · `uv run ruff check <owned paths>` · `uv run ruff format --check <owned paths>`. The project declares no typecheck command, so none is run.
- main session after each DAG level: `uv run pytest -m "not live"` · `uv run ruff check` · `uv run ruff format --check`.
- main session after level 2 (J): `uv run pytest -m live tests/test_e2e_gate.py` (AC-45; spends credits; only with Glib's go and `FACTORY_JUDGE_MODEL` set).

## Checks for reviewers
- sdd-engineering:plan-verifier: every red-first AC through `uv run pytest -m "not live" tests/<file> -k ac<N>`; AC-45 from the main session's live run output and the stored card (plan-verifier never runs live); browser ACs reported as main-session items.
- architecture-review:architecture-reviewer: no SDK import (`pipecat`, `pipecat_boson`, `anthropic`, `httpx`, `fastapi`) outside `factory/runtime/boson_session.py`, `factory/gate/tts_boson.py`, `factory/gate/judge_anthropic.py`, `factory/agent_spec/brief_anthropic.py`, `factory/web/`, `factory/composition.py` (the composition root builds the SDK clients; Glib, 2026-10-24, finding A1); env reads only in `factory/composition.py`; no import from `vendor-ref`; layering per Constraints. No boundary lint is declared, so the reviewer reads the imports.
- security: `/security-review` of the diff (prompt-injection framing of the judge prompt, key handling, recording path, error-text rendering).
- main session: `/code-review` of the diff; the live AC-45 run; browser checks AC-36, AC-38 to AC-42, AC-49, AC-52; `docs/CLAIMS.md` rows for every number on the stage card; `docs/boson-protocol.md` updated with what the first audio-mode run shows (usage in audio mode, F2; VAD close on silence; transcript at barge-in).

## Commands for the read-only agents
These are all covered by the existing `.claude/agent-guard.json` entries (exact prefix match), so no guard edit and no `CLAUDE.md` Check-table edit is needed for them:
- `uv run pytest -m "not live"`, run by plan-verifier
- `uv run pytest -m "not live" tests/<file>.py -k ac<N>`, run by plan-verifier (prefix of the first entry)
- `uv run ruff check`, run by architecture-review:architecture-reviewer
- `uv run ruff format --check`, run by architecture-review:architecture-reviewer

Main-session edit: add a `CLAUDE.md` Check-table row `| Live gate (AC-45) | \`uv run pytest -m live tests/test_e2e_gate.py\` | Boson + Anthropic APIs, spends credits |`. Its Network column is not `none`, so `tests/test_scaffold.py` stays green and the guard stays unchanged. Never add a bare `uv run pytest` prefix to the guard: it would also allow `-m live`.

## Out of scope
- Writing or changing the spec (spec-creator), architecture review (architecture-review:architecture-reviewer), acceptance verification (plan-verifier), security review and end-to-end runs (main session and security reviewer).
- P3 avatar (L5): no ACs in the spec.
- Template content for Health Insurance, Fraud Detection, Customer Support and AI Receptionist (card texts missing).
- The real generator adapter until its ADR is answered (step 6b).
- Converting Spec B's IHBench output (waits on its format).
- Input transcription (F19), telephony, auth, multi-user.

## Risks
- pipecat-boson private API: the tap subclass depends on `_dispatch_boson_server_event`, `_ws_send` and `_mark_websocket_disconnected` of 0.1.4; pin it exactly. If the step 8 spike fails in 30 min, L2 returns `blocked`, and Glib decides between a thin WS adapter in the shape of `scripts/smoke.py` behind the same `RealtimeSession` port (reopens `docs/reuse-map.md:8`) or stopping at a P1 without a live gate. Dispatch `research-tools:researcher` on how `OpenAIRealtimeLLMService` from pipecat-ai < 1.13 runs outside a full pipeline and how it handles an unregistered function call. The base class is not in `vendor-ref/`.
- Audio budget: streamed silence counts as input audio, so 6 scenarios × (user turn + assistant reply, both streamed in real time) must fit in 240 s. Keep 1–2 short turns per scenario, set `max_output_tokens`, and ask for two-sentence answers; otherwise the stage card reads "incomplete, budget reached". Measure on the first live run and trim scenarios before the demo.
- UNVERIFIED Boson behaviour the gate leans on (`docs/boson-protocol.md` UNVERIFIED list): whether server VAD closes a turn on streamed silence, whether the transcript is cut at barge-in, and whether audio-mode `usage` arrives (F2). The first AC-45 run settles each one; record the findings in `docs/boson-protocol.md` (main session).
- TTS 3 non-streaming sample rates are UNVERIFIED (F22), so only `stream: true` + `pcm` is used.
- `results/` is git-ignored, so the stage card is local only. For `docs/CLAIMS.md` traceability the main session should copy the shown card into a tracked path or cite its run id with the file kept on the laptop.
- No typecheck is declared; Glib's global rule wants mypy for new code, but the project's Check table wins. Adding one is a separate decision.
- Time: 3 h 20 min to the talks. Lane 0 waits on the dependency ADR answer; every minute there delays all of level 1.
- External facts needed → dispatch `research-tools:researcher`: pipecat base-class behaviour (above); the Anthropic model id and its price per call for the judge ADR.

