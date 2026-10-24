# Verification: Higgs Agent Factory (P1)

Date: 2026-10-24
Plan: `docs/plans/2026-10-24-higgs-agent-factory.md`
Spec: `specs/2026-10-24-higgs-agent-factory.md`
Range reviewed: `64de2c4..main` (branch `chore/finalize-hackathon`), then one fix pass in the working tree (uncommitted).
Reviewers: plan-verifier, architecture-review, security, correctness. Fix pass: implementer in fix mode.

## Plan-verifier report (verbatim)

# Plan Verification: Higgs Agent Factory (P1)
Target: 64de2c4..main (branch chore/finalize-hackathon)
Overall: gaps (only the intentionally cut/pending items are not met; no must-close)
Counts: 52 met, 3 partial, 9 not met (all cut/pending on purpose), 8 unverifiable, 0 unmapped code hunks

## Checks
| check | command | result | verdict |
|---|---|---|---|
| offline tests | `uv run pytest -m "not live" -q` | 179 passed, 1 deselected, 4 xfailed, 1 warning | met |
| lint | `uv run ruff check` | All checks passed! | met |
| format | `uv run ruff format --check` | 67 files already formatted | met |
| AC-55..62 + AC-23 + scaffold + e2e collect | `pytest -m "not live" -k "ac45 or scaffold or ac55..ac62 or ac23"` | 14 passed | met |
| templates | `pytest -m "not live" tests/test_templates.py -rx` | 9 passed, 4 xfailed (card text pending, strict xfail as planned) | met |

## Steps
| item | verdict | evidence |
|---|---|---|
| 1 deps + pythonpath | met | pyproject.toml deps `pipecat-boson==0.1.4`, anthropic, httpx, pydantic; `pythonpath = ["."]`; test_contracts::test_factory_importable passes; test_scaffold passes |
| 2 Agent Spec schema | met | factory/agent_spec/models.py, validation.py; tests/test_agent_spec_schema.py incl. test_recording_path_must_stay_in_recordings_dir pass |
| 3 ports, records, doubles, fake server | met | factory/ports.py, gate/records.py, tests/doubles.py, fake_realtime_server.py, conftest.py; test_contracts.py passes |
| 6 generator | met | factory/agent_spec/generator.py:10 `MAX_BRIEF_CHARS = 1000`; tests/test_generator.py passes |
| 6b Anthropic BriefModel | met | factory/agent_spec/brief_anthropic.py; test_brief_wrapped_as_data passes |
| 7 templates | met | specialist_training.json, templates/__init__.py, recordings/.gitkeep; 4 strict xfails |
| 8 spike | met | boson_session.py (tap subclass); test_spike_one_turn passes |
| 9 end causes, refused config | met | test_ac14/15/16/20 in test_runtime_session.py pass |
| 10 tool calls on wire | met | test_ac21_server_web_search_no_reply, test_ac22_tool_output_sent pass |
| 11 transcript, usage, speech events | met | test_usage_and_transcript_mapping passes |
| 12 preflight | met | runner.py:82 message with both counts; test_ac4, test_ac46 pass |
| 13 TTS cache | met | tts_cache.py, tts_boson.py; test_ac8, test_cache_key_is_text_and_voice, ac10 pass |
| 13b recording fallback | met | test_ac9_recording_fallback_marked_recorded passes |
| 14 playback and TTFA | met | playback.py; test_chunks_stay_under_f4_limit, ac47, ac25 pass |
| 15 judge | met | judge.py, judge_anthropic.py; tests/test_judge.py passes (no_retries test present) |
| 16 run loop | met | runner.py; tests/test_gate_runner.py passes |
| 16c response-start event, per-session doubles | met | test_response_created_maps_to_event, test_fake_server_scripts_per_connection pass |
| 16d one session per scenario | met | test_ac55, test_ac56 pass |
| 16e 2 s quiet window | met | runner.py:52 QUIET_WINDOW_S; test_quiet_window_default_is_two_seconds, ac57, ac58, ac60 pass |
| 16f TTFA first response | met | test_ac59 passes |
| 16g responses per turn | met | test_ac61, test_card_roundtrip_keeps_responses pass; card .txt line 13 shows "Responses per turn" |
| 16h st-5 rewording | met | test_no_scripted_turn_has_an_internal_sentence_break, test_st5_rubric_unchanged pass |
| 16i wire with several sessions | met | test_wire_one_connection_per_scenario passes |
| 16j keep invalid judge reply | met | judge.py:16 RAW_REPLY_MAX_CHARS=2000; test_ac63, test_valid_reply_keeps_no_raw pass |
| 16k diagnostics in record and card | met | test_ac62_* in test_gate_runner.py and test_card_store.py, test_card_without_diagnostics_still_loads pass |
| 16l render hides raw reply | met | test_ac64_render_hides_raw_reply passes |
| 16m st-5 rubric F27 | met | test_no_criterion_asks_judge_to_see_a_cut_off passes |
| 17b expected call match | met | test_ac23_* pass |
| 17c barge-in timing | met | test_ac28_bargein_stop_time, test_ac28_reply_too_short... pass |
| 18 verdict | met | verdict.py; tests/test_verdict.py passes |
| 19 TTFA metrics | met | metrics.py; test_percentile_method_nearest_rank, test_ac27_* pass |
| 19b scripted only | met | test_ac48_scripted_only passes |
| 20b barge-in aggregate | met | test_ac29_ac54_not_measured_excluded passes; card line 12 "p50 272 ms, max 272 ms" |
| 21 cost | met | cost.py:9 `AUDIO_IN_USD_PER_MIN = 0.0023  # F12`, :17 AUDIO_COST_LABEL, :19 TOKEN_NOT_MEASURABLE verbatim; test_cost.py passes |
| 21b measured token cost | not met | pending on purpose: cost.py has no token_cost with rates or TOKEN_COST_LABEL; card shows token counts only (line 16) |
| 21c token headline | not met | pending on purpose (depends on 21b) |
| 22 card builder and store | met | card_builder.py, card_store.py; test_ac33_two_runs_two_cards, test_same_second_runs_distinct_ids pass |
| 22b IHBench RQ | not met | pending on purpose: no factory/gate/ihbench.py; card prints "IHBench RQ: not available" |
| 23 composition and CLI | met | composition.py, __main__.py; tests/test_gate_wire.py passes |
| 24 live e2e | met (collected) | tests/test_e2e_gate.py collected and deselected under -m "not live"; live run itself: main session (see AC-45) |
| 25 web deps | not met | P2 cut on purpose; pyproject has no fastapi/uvicorn |
| 26 live session service | not met | P2 cut on purpose; no factory/live/ |
| 27 demo server | not met | P2 cut on purpose; no factory/web/ |
| 28 demo page | not met | P2 cut on purpose; no factory/web/static/ |

## Acceptance criteria
| item | verdict | evidence |
|---|---|---|
| AC-1, AC-2 | met | test_generator.py::test_ac1_*, test_ac2_overlong_brief_refused_no_call pass |
| AC-3 | partial | Specialist Training case passes; 4 other templates strict xfail "card text pending" (expected per plan) |
| AC-4, AC-46, AC-5, AC-6, AC-7 | met | named tests pass (gate_runner, templates, agent_spec_schema) |
| AC-8, AC-9, AC-10 | met | test_tts_cache.py::test_ac8/ac9, test_gate_runner.py::test_ac10 pass |
| AC-11, AC-12, AC-13, AC-18, AC-19 | met | test_judge.py, test_verdict.py pass |
| AC-14, AC-15, AC-16, AC-17, AC-20 | met | adapter and runner halves pass |
| AC-21, AC-22, AC-24 | met | test_runtime_session.py, test_gate_runner.py pass |
| AC-23 | met | test_ac23_expected_call_matched_and_not and record test pass |
| AC-25, AC-47, AC-28 | met | test_playback.py passes |
| AC-27, AC-48, AC-29, AC-54 | met | test_metrics.py passes |
| AC-30, AC-31, AC-32 (card half) | met | test_cost.py passes; AC-32 page half not built (step 27) |
| AC-33 | met | test_ac33_two_runs_two_cards, test_ac33_never_overwrites pass |
| AC-55..AC-64 (spec deltas) | met | ac55, ac56, ac57, ac58, ac59, ac60, ac61, ac62, ac63, ac64 tests pass |
| AC-45 | met | not re-run (plan-verifier never runs live); stored card docs/evidence/eval-card-20261024T164057Z-9e2ee667.txt: verdict rejected, n = 7, 0.80 min in, 0.70 min out, estimated audio cost $0.0116. Live run: main session |
| AC-34 | not met | step 22b pending on purpose |
| AC-50, AC-51 | not met | steps 21b/21c pending on purpose |
| AC-26, AC-35 | not met | step 26 cut (P2) |
| AC-37, AC-43, AC-44, AC-53 | not met | step 27 cut (P2) |
| AC-32 page half | not met | step 27 cut (P2) |
| AC-36, AC-38..42, AC-49, AC-52 | unverifiable | browser checks: main session; page not built (step 28 cut) |

## Reviewer checks
| item | verdict | evidence |
|---|---|---|
| boundary check | unverifiable | owner: architecture-review:architecture-reviewer |
| security review | unverifiable | owner: security reviewer |
| /code-review, live AC-45 rerun, CLAIMS rows | unverifiable | owner: main session |
| red-first evidence | partial | no red-sha and no Implementation Report in the brief, so the "failing before passing" runs are not shown; green only |

## Unmapped changes
- none in code: all factory/ and tests/ files map to steps 1 to 23, 24.
- Docs hunks, mapped to main-session items in the plan: STATUS.md, docs/CLAIMS.md, docs/FRICTION.md, docs/boson-protocol.md (plan Checks: main session), specs/2026-10-24-higgs-agent-factory.md and the plan file (spec/plan deltas 16c to 16m), docs/evidence/eval-card-*.json/.txt (AC-45 evidence).
- uv.lock: generated, maps to step 1.

## Insight candidates
- Several planned test names were renamed in implementation (for example test_ac18_judge_invalid_incomplete became test_ac18_cause_makes_incomplete_even_if_labels_pass; test_ac13_all_pass_released became test_ac13_all_pass_releases). `-k ac<N>` still finds them.
- AC-54 and AC-55..64 are in the spec and plan deltas but not in the plan's verbatim AC list.

---

## Findings after the fix pass

Statuses: FIXED (closed in the working tree with a test), REFUTED, OPEN (real, no fix yet), NEEDS-GLIB (needs a decision before anyone fixes it).

### Architecture (verdict: fail before the fix pass)

| # | severity | file:line | finding | status |
|---|---|---|---|---|
| A1 | must-close | factory/composition.py:16 | Imports `anthropic` and `httpx` and catches `anthropic.APIError` (:75); composition.py is not on the SDK allow-list at plan line 642 | CLOSED by plan text: Glib (2026-10-24) put `factory/composition.py` on the SDK allow-list (plan Constraints and Checks for reviewers) |
| A2 | must-close | factory/__main__.py:69 | CLI entry read `os.environ`; plan says env reads only in composition.py | FIXED. `__main__.py` no longer imports `os`; `build_app` takes `Mapping[str, str] \| None` and resolves `os.environ` itself. Test `test_cli_leaves_the_environment_read_to_the_composition_root` added (not run red-first) |
| A3 | should (default heuristic) | factory/gate/tts_cache.py:64 | Service-layer disk I/O with no port; `run_gate` takes the concrete `TurnAudioSource`; `FactoryApp.store` typed `FileCardStore` though `CardStorePort` exists | OPEN. No project rule requires it; no action required |

### Security (no must-close)

| # | severity | file:line | finding | status |
|---|---|---|---|---|
| S1 | should | factory/agent_spec/models.py:90 | Budget fields accept NaN and Infinity; no system-wide ceiling on brief-sourced budgets, so AC-17's audio cap can be switched off. Probe: `NaN ACCEPTED nan`, `Infinity ACCEPTED inf` | OPEN |
| S2 | should | factory/agent_spec/validation.py:66 | A brief-sourced spec can enable server `web_search`; spec "Untrusted inputs" says generator output adds only mocked client tools | OPEN (fix: reject `kind == "server"` for brief sources, or record a decision and change the spec text) |
| S3 | should | factory/composition.py:96 | Agent and scenario ids are unchecked until card save; `../../etc` passes preflight, runs the paid gate, then raises an uncaught `ValueError` and stores no card. Traversal itself is blocked | OPEN |
| S4 | nit | factory/agent_spec/brief_anthropic.py:48 | Single-pass `</brief>` strip: `</bri</brief>ef>` becomes `</brief>` | OPEN |

### Correctness

| # | severity | file:line | finding | status |
|---|---|---|---|---|
| C1 | must-close | factory/gate/runner.py:534 | Barge-in recorded as measured when the interrupted response ends `completed`; AC-29 requires "not measured" | FIXED. `bargein_ms` set only when `event.status == "cancelled"`. `test_ac29_completed_interruption_is_not_measured` failed red with `(399.99..., 'measured') != (None, 'not measured')`, now green with `test_ac29_cancelled_interruption_is_measured`. AC-29 "no `response.done`" case: NEEDS-GLIB (harness aborts the gate instead of recording "not measured"; never records "measured" on that path) |
| C2 | should | factory/gate/runner.py:485 | `turn_detection: null` passes preflight but the runner never commits or asks for a response; the gate waits forever (repro: still waiting after 10 s) | OPEN |
| C3 | should | factory/gate/runner.py:485 | Reply waits have no deadline (interrupted response with no `response.done`, client-tool follow-up); client-tool auto-continuation is UNVERIFIED in boson-protocol.md | OPEN (needs a live check and an F-row) |
| C4 | should | factory/runtime/boson_session.py:282 | Server `web_search` ToolCall emitted on `output_item.added`; arguments that arrive on `output_item.done` are dropped. Not on the demo path (`tools: []`) | OPEN |
| C5 | nit | factory/gate/runner.py:75 | Brief-generated budgets are not capped (probe: `max_audio_s_per_run=1000000000.0` accepted) | OPEN (same root as S1) |

### Plan-verifier findings

| # | severity | file | finding | status |
|---|---|---|---|---|
| P1 | nit | docs/plans/2026-10-24-higgs-agent-factory.md | Red-first evidence missing for the original implementation: no red-sha, green runs only | OPEN (the fix pass shows red-first for C1 only) |
| P2 | nit | factory/gate/cost.py | Steps 21b/21c (AC-50/51) and 22b (AC-34) not built | NEEDS-GLIB (pending on purpose) |

## Check commands

Before the fix pass (plan-verifier, correctness):

| command | result |
|---|---|
| `uv run pytest -m "not live" -q` | `179 passed, 1 deselected, 4 xfailed, 1 warning` |
| `uv run ruff check` | `All checks passed!` |
| `uv run ruff format --check` | `67 files already formatted` |
| `uv run pytest -m "not live" -q -rx tests/test_templates.py` | `9 passed, 4 xfailed` |

After the fix pass (fix report):

| command | exit | result |
|---|---|---|
| `uv run pytest -m "not live" -q` | 0 | `182 passed, 1 deselected, 4 xfailed, 1 warning in 24.24s` |
| `uv run ruff check` | 0 | `All checks passed!` |
| `uv run ruff format --check` | 0 | `70 files already formatted` |

Not run by this loop: live tests (`-m live`), mypy, browser checks. AC-45 rests on the stored card
`docs/evidence/eval-card-20261024T164057Z-9e2ee667.txt`.
