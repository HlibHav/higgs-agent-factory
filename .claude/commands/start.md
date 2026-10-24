---
description: Start a session — read in order, restate the task, wait for go if it is not in an approved plan
---

Task: $ARGUMENTS

1. Read in the order `CLAUDE.md` gives under "Before answering": `STATUS.md`, `CLAUDE.md`,
   `factory/INSIGHTS.md` (through `engineering-paved-path:engineering-insights`),
   `docs/boson-protocol.md` if the task touches the Boson API, then the active spec in `specs/`
   and its plan in `docs/plans/`.
2. Restate in one paragraph: the task, the files you will touch, and the acceptance command
   (from the `## Check` table, or the plan's check for this step) that will prove it done.
3. If the task is not a step of a plan whose spec has `Status: approved`, stop and wait for
   Glib's "go". Do not edit anything before that.
