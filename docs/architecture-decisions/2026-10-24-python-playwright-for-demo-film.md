---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: harness
---

# Drive the demo-film takes with Python Playwright and Chromium

## Context and Problem Statement
The demo film (`specs/2026-10-24-demo-film.md`, `docs/demo-film/screenplay.md`) is recorded with no human at the keyboard. A script has to open the demo page, replace its microphone with pre-generated Higgs TTS lines, watch the page's WebSocket frames to time the interruption, capture the page's audio and record the picture. The repo is Python 3.12 with uv and pytest (`live` marker); it has no browser automation today.

## Considered Options
- Python Playwright as a uv dependency, plus a Chromium download.
- Node Playwright in a separate folder, as in the Dev Digest `record-demo.js` precedent.
- Chrome DevTools Protocol directly over a WebSocket, no library.

## Decision Outcome
Chosen option: Python Playwright, because it keeps the recorder in the repo's one language, its init scripts and `page.on("websocket")` cover the fake microphone and the interruption trigger, and live takes run under the existing `live` marker next to the offline tests.

### Consequences
- Good: one toolchain for the recorder and its tests; built-in page video and WebSocket frame events.
- Good: offline parts (timeline math, take log, claims gate, TTS cache keys) test with plain pytest.
- Bad: a new dependency and a Chromium download (`playwright install chromium`) outside `uv.lock`.
- Bad: Playwright's page video has no audio, so the take audio is captured inside the page and muxed by ffmpeg (a system binary).

### Confirmation
`pyproject.toml` lists `playwright` (added through `uv add`); the recorder's live tests carry `@pytest.mark.live`; the offline suite passes without a browser installed.

## More Information
- Spec: `specs/2026-10-24-demo-film.md`
- Graphics: `docs/architecture-decisions/2026-10-24-remotion-for-demo-film-graphics.md`
