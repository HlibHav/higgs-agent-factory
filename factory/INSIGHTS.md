# factory — insights

Insert-only. Format and rules: `engineering-paved-path:engineering-insights` (`reference.md`).

## What Works

- 2026-10-24: A server-VAD barge-in ends the interrupted response `cancelled`, like a client `response.cancel` (F28): live gate `20261024T171443Z-35b3f15b` measured barge-in 117 ms under the AC-29 rule.

- 2026-10-24: The live page proxies browser PCM through one FastAPI WebSocket with a single writer queue; a scripted client with cached TTS audio is a cheap end-to-end check of `/ws/live/<agent>` before touching a mic (`docs/DEMO-RUNBOOK.md`).

## What Doesn't Work

- 2026-10-24: Judging barge-in from the transcript: the transcript arrives whole (F27). Barge-in is measured only when the interrupted response ends `cancelled` (AC-29 fix, `factory/gate/runner.py`).

## Codebase Patterns

- 2026-10-24: Env is read only in `factory/composition.py` (`build_app(None, …)` resolves `os.environ`); entries pass nothing. SDK imports stay in adapters; composition.py is the open exception (finding A1, waiting on Glib).

- 2026-10-24: Agent Spec v2 keeps `instructions`/`tools`/`scenarios` as plain `@property` views over persona + skills, so runtime, runner and live session did not change; a `mode="before"` validator lifts flat v1 dicts (fixtures, old cards). Plain properties stay out of `model_dump` and the JSON schema the generator sees; `computed_field` would leak them.
- 2026-10-24: Skill-level grouping changed the outcome. The flat spec failed only st-6 (5/6), while the same policy split into skills failed st-2 and st-6 (4/6, run `20261024T174839Z-6f4ab3b5`). Compare cards across contract versions with care.
- 2026-10-24: The coach overfits to the visible test. Its refund procedure quoted st-2's own "30 euros" example. Coach prompts see the failing transcript, so a released v2 proves the loop, not generalisation. Held-out scenarios per skill would test that.

- 2026-10-24: No tool-using agent had been live-gated until a brief agent was. The first run hung forever after the mocked tool output: the server needs `response.create` (F29), and the runner waited for the follow-up with no timeout. Live-gate one template per code path (tools, interrupts) before calling a path done.

- 2026-10-24: One run per scenario is noisy. On `brief-onboarding-buddy-b948ed`, book-call-slot-taken went PASS → FAIL between v1 and v2 although the coach had not touched its skill. The k = 2 judge only measures judge noise, not agent noise. Running each scenario n times (pass^n) would separate the two.
- 2026-10-24: The coach page diff compares the latest card with its parent (v2 → v3), not with the first version. Read the chain of parent run ids for the full story.

- 2026-10-24 (film): The demo page creates its AudioContext only on the Start click, but the film recorder loads caller audio and starts the take before that. `tap.js` makes the 24 kHz context early and hands it back to the page's `new AudioContext`. The spike missed this because it started live first; drive the real run order in a spike.
- 2026-10-24 (film): A take is a "candidate" when the agent's audio stopped on T2, which says nothing about what it said next. In run `20261024T203615Z-34b33d` take 2 passed the audio rule while its reply answered T1. The T2 transcript in the take log is what catches it; the keeper stays a human call.
- 2026-10-24 (film): At 1920×1080 the page's TTFA readout sits near y ≈ 2500 of a 2613 px page, out of frame. `tap.js` scrolls it into view; `test_ttfa_label_in_viewport` is the canary if the page layout changes.

## Tool & Library Notes

- 2026-10-24: `AsyncAnthropic.messages.create` is overloaded; a Protocol member typed as a read-only property returning `Callable[..., Awaitable[Any]]` satisfies mypy, a plain `async def create(**kwargs)` does not.
- 2026-10-24: pipecat and pipecat-boson ship no type hints; mypy ignores them per module (`pyproject.toml`).
- 2026-10-24 (film): Homebrew ffmpeg 9.0.1 has neither `subtitles` nor `drawtext`, so captions are a transparent ProRes 4444 overlay rendered by Remotion and laid on with `overlay`. The concat demuxer resolves relative list entries against the list file's folder: write absolute paths.
- 2026-10-24 (film): `/opt/anaconda3/bin/node` (v20) shadows Homebrew's node 24 on PATH; run `demo-film-graphics` with `/opt/homebrew/bin` first. Remotion 4.0.528 needs zod pinned to exactly 4.5.4.
- 2026-10-24 (film): Chromium accepts a MediaStream built with `createMediaStreamDestination()` in the page's own context as the result of an overridden `getUserMedia`, headless, with no fake-device flag or permission grant.

## Recurring Errors & Fixes

## Session Notes

## Open Questions

- 2026-10-24: Does a server-VAD barge-in cancel behave like a client `response.cancel` (F28 covers only the latter)?
