---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: backend
---

# Add pydantic, anthropic and httpx as runtime dependencies

## Context and Problem Statement
P1 needs an Agent Spec schema whose validation errors name the failing field (spec AC-1), an Anthropic client for the judge and generator, and an HTTP client for Higgs TTS 3 (F22). `pipecat-boson==0.1.4` is already decided (`docs/reuse-map.md`). P2's demo page would need a web server.

## Considered Options
- `pydantic`, `anthropic`, `httpx`; `fastapi` + `uvicorn` only when P2 starts.
- Minimal: `dataclasses` + `jsonschema` instead of pydantic, `urllib` instead of httpx, `anthropic` kept.

## Decision Outcome
Chosen option: `pydantic`, `anthropic`, `httpx` (with `fastapi` and `uvicorn` deferred to P2), because pydantic gives field-named validation errors for AC-1 for free, httpx streams TTS PCM cleanly, and it matches Glib's default stack. The Anthropic client is built with `max_retries=0`, since the spec's NFR forbids hidden retries.

### Consequences
- Good: less hand-written validation and HTTP code under time pressure.
- Bad: three more dependencies in `uv.lock`; pydantic models become part of the contract surface.

### Confirmation
Lane 0 of the plan adds them with `uv add`; `uv.lock` records the versions; a test asserts the Anthropic client is constructed with `max_retries=0`.

## More Information
Plan: `docs/plans/2026-10-24-higgs-agent-factory.md` (lane 0, open questions). Glib's answer in chat, 2026-10-24.
