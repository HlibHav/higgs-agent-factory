---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: harness
---

# Render the demo-film graphic beats with Remotion in a self-contained folder

## Context and Problem Statement
Four beats of the demo film have no live page in them: the hook card (v1 REJECTED), the market layers, the decision card and the end card with its sources (`docs/demo-film/screenplay.md`). They need motion (a row lighting up, numbers appearing) and must carry exactly the numbers that `docs/CLAIMS.md` allows.

## Considered Options
- HTML/CSS cards opened and recorded by the same Playwright browser.
- Pillow stills composited with ffmpeg, as in the MBH Publicis film.
- Remotion (React compositions rendered to video).

## Decision Outcome
Chosen option: Remotion, by Glib's call, because it gives the richest control of motion and timing for the graphic beats and the Remotion skills are installed for this work. It lives in its own folder with its own `package.json`; the Python side only consumes the rendered video files.

### Consequences
- Good: frame-exact animation and timing, previewable in Remotion Studio.
- Good: the Python recorder stays independent; ffmpeg joins the rendered beats with the page takes.
- Bad: Node and npm enter the repo, in one folder, with their own lockfile.
- Bad: Remotion's own tests are outside the Python suite; the numbers it shows must come from one data file that the claims gate also reads, so the gate still covers them.

### Confirmation
The Remotion folder renders headless with one command; the claims gate reads the same data file the compositions read and fails the render when a number has no `ok` row in CLAIMS.

## More Information
- Spec: `specs/2026-10-24-demo-film.md`
- Browser: `docs/architecture-decisions/2026-10-24-python-playwright-for-demo-film.md`
