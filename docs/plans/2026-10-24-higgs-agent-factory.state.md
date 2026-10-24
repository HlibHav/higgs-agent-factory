# Plan state: Higgs Agent Factory

Plan: `docs/plans/2026-10-24-higgs-agent-factory.md`
Spec: `specs/2026-10-24-higgs-agent-factory.md`
Updated: 2026-10-24, after the review loop (plan-verifier, architecture, security, correctness) and one fix pass.
Branch: `chore/finalize-hackathon`. Reviewed range: `64de2c4..main`.

Fix-pass changes are in the working tree and not committed: `factory/gate/runner.py`, `factory/__main__.py`,
`factory/composition.py`, `tests/test_gate_runner.py`, `tests/test_gate_wire.py`.

Commits are mapped by lane from the commit subjects: lane 0 `7502cd6`, L1 `30a537d`, L2 `4bdf47a`,
L3r `4984cc4`, L3c `b9a6904`, J `f3d6478`, delta 16c-16i `2460473`, delta 16j-16m `ab2eae2`,
live evidence `b29bde5`.

| step | title | state | commit / evidence |
|---|---|---|---|
| 1 | dependencies and test path | done | `7502cd6`; `pipecat-boson==0.1.4`, `pythonpath = ["."]`; test_contracts and test_scaffold pass |
| 2 | Agent Spec schema and validation | done | `7502cd6`; tests/test_agent_spec_schema.py passes |
| 3 | ports, records, doubles, fake server | done | `7502cd6`; tests/test_contracts.py passes |
| 6 | brief generator | done | `30a537d`; `MAX_BRIEF_CHARS = 1000`; tests/test_generator.py passes |
| 6b | Anthropic BriefModel adapter | done | `30a537d`; test_brief_wrapped_as_data passes |
| 7 | templates | done (Specialist Training only) | `30a537d`; 4 other templates strict xfail "card text pending", as planned |
| 8 | pipecat-boson spike | done | `4bdf47a`; test_spike_one_turn passes |
| 9 | end causes, refused config | done | `4bdf47a`; test_ac14/15/16/20 in test_runtime_session.py pass |
| 10 | tool calls on the wire | done | `4bdf47a`; test_ac21, test_ac22 pass |
| 11 | transcript, usage, speech events | done | `4bdf47a`; test_usage_and_transcript_mapping passes |
| 12 | preflight | done | `4984cc4`; test_ac4, test_ac46 pass |
| 13 | TTS cache and audio source | done | `4984cc4` (+ `1ad12f5` TTS model field); test_ac8, test_ac10 pass |
| 13b | recording fallback | done | `4984cc4`; test_ac9_recording_fallback_marked_recorded passes |
| 14 | paced playback and TTFA | done | `4984cc4`; test_ac25, test_ac47 pass |
| 15 | judge and Anthropic adapter | done | `4984cc4`; tests/test_judge.py passes |
| 16 | gate run loop | done | `4984cc4`; tests/test_gate_runner.py passes |
| 16c | response-start event, per-session doubles | done | `2460473`; test_response_created_maps_to_event passes |
| 16d | one session per scenario | done | `2460473`; test_ac55, test_ac56 pass |
| 16e | 2 s quiet window | done | `2460473`; test_ac57, test_ac58, test_ac60 pass |
| 16f | TTFA on the first response | done | `2460473`; test_ac59 passes |
| 16g | responses per turn | done | `2460473`; test_ac61 passes |
| 16h | st-5 rewording | done | `2460473`; test_no_scripted_turn_has_an_internal_sentence_break passes |
| 16i | wire with several sessions | done | `2460473`; test_wire_one_connection_per_scenario passes |
| 16j | keep invalid judge reply, capped | done | `ab2eae2`; test_ac63 passes |
| 16k | diagnostics in record and card | done | `ab2eae2`; test_ac62_* pass |
| 16l | render hides the raw reply | done | `ab2eae2`; test_ac64_render_hides_raw_reply passes |
| 16m | st-5 rubric drops undecidable criteria (F27) | done | `ab2eae2`; test_no_criterion_asks_judge_to_see_a_cut_off passes |
| 17b | expected tool call match | done | `4984cc4`; test_ac23_* pass |
| 17c | interrupting turns, barge-in timing | done, fixed in review | `4984cc4`; correctness must-close (completed response counted as measured) fixed in the working tree: `bargein_ms` set only on `status == "cancelled"`; test_ac29_completed_interruption_is_not_measured red then green |
| 18 | verdict | done | `b9a6904`; tests/test_verdict.py passes |
| 19 | TTFA metrics | done | `b9a6904`; test_ac27_* pass |
| 19b | scripted-only filter | done | `b9a6904`; test_ac48_scripted_only passes |
| 20b | barge-in aggregate | done | `b9a6904`; test_ac29_ac54_not_measured_excluded passes |
| 21 | cost | done | `b9a6904`; `AUDIO_IN_USD_PER_MIN = 0.0023  # F12`; tests/test_cost.py passes |
| 21b | measured token cost | not started — pending Glib's decision | no `token_cost` / `TOKEN_COST_LABEL`; waits on the cached-token counting answer |
| 21c | token headline | not started — pending Glib's decision | depends on 21b |
| 22 | card builder and store | done | `b9a6904`; test_ac33_* pass |
| 22b | IHBench RQ | not started — pending Glib's decision | no `factory/gate/ihbench.py`; card prints "IHBench RQ: not available" |
| 23 | composition root and CLI | done, partly fixed in review | `f3d6478`; env read moved into `build_app` (working tree); SDK imports in composition.py still NEEDS-GLIB |
| 24 | live end-to-end gate | done | `b29bde5`; docs/evidence/eval-card-20261024T164057Z-9e2ee667.txt: verdict rejected, n = 7, 0.80 min in, 0.70 min out, $0.0116 estimated audio cost |
| 25 | P2 web dependencies | not started — pending Glib's decision | outside the reviewed range, `67c8f7b` adds fastapi and uvicorn (ADR 2026-10-24); no code uses them yet |
| 26 | P2 live session service | not started — pending Glib's decision | no `factory/live/` |
| 27 | P2 demo server | not started — pending Glib's decision | no `factory/web/` |
| 28 | P2 demo page | not started — pending Glib's decision | no `factory/web/static/` |

## Open after the loop
- NEEDS-GLIB: composition.py imports `anthropic`/`httpx` and catches `anthropic.APIError` (plan allow-list, line 642). Recommended option (a): add composition.py to the allow-list and move the `APIError` mapping into the adapters behind a port-level error.
- NEEDS-GLIB: AC-29 "no `response.done` before the scenario ends" case. The harness aborts the gate instead of recording "not measured"; it never records "measured" on that path.
- OPEN (should): budget NaN/Infinity and no system ceiling on brief-sourced specs; brief can enable server `web_search`; agent and scenario ids unchecked until card save; `turn_detection: null` hangs; reply waits unbounded; server `web_search` arguments dropped on `output_item.done`.
- Fix-pass changes are uncommitted.
