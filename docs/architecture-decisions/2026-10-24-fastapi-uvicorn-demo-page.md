---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: backend
---

# Serve the P2 demo page with FastAPI and uvicorn; add mypy as a typecheck gate

## Context and Problem Statement
P2 (spec AC-36…44, AC-49, AC-52, AC-53; plan steps 25–28) needs one local page that shows the template cards, the Agent Spec, the stored Eval Card, a single-scenario check, and a live voice session where the browser streams microphone PCM to our server and the server talks to Higgs Realtime. API keys must stay server-side (AC-37), so the browser cannot open the Boson WebSocket itself. The earlier ADR (`2026-10-24-pydantic-anthropic-httpx.md`) deferred the web server to P2.

## Considered Options
- FastAPI + uvicorn: async HTTP and WebSocket routes on Starlette, one process, `TestClient` for offline tests.
- Bare Starlette + uvicorn: the same server, fewer conveniences (no request models, no dependency injection).
- `websockets` server + a static file server: two servers, hand-rolled routing, no test client.

## Decision Outcome
Chosen option: FastAPI + uvicorn, because it is Glib's default stack, it serves the page, the JSON routes and the live WebSocket from one asyncio process (the same loop that runs `pipecat-boson`), and its `TestClient` lets the AC-37/43/44/53 tests run offline against the fake Realtime server. The server binds to `127.0.0.1` only.

Also decided the same day: `mypy` is added as a dev dependency and `uv run mypy` becomes an offline check in `CLAUDE.md` (pipecat and pipecat-boson are untyped and are excluded through a per-module override).

### Consequences
- Good: one process, testable offline, keys never leave the server.
- Bad: two more runtime dependencies (`fastapi` pulls `starlette`); the live page is a single-user local tool, not production (spec non-goal).

### Confirmation
`uv add fastapi uvicorn` and `uv add --dev mypy` record the versions in `uv.lock`; `tests/test_web.py` covers AC-37 (no key in any page response or message); `uv run mypy` is green and listed in the Check table and `.claude/agent-guard.json`.

## More Information
Glib's answer in chat, 2026-10-24 ~12:55 Toronto: "Давай робити з FastAPI та Uvicorn P2 … максимально стабільним і надійним із першого разу"; mypy: "Виправити + гейт".
