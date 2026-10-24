# specs/

Normative specs: what a feature must do and why, never how to build it (that is the plan in
`docs/plans/`). This is a single-package repo, so every spec lives here.

## Conventions

- **File name:** `YYYY-MM-DD-<kebab-feature-name>.md`, dated the day the spec is created. An
  update keeps the file and its date and adds a `## Changelog` row. There is no `-v2`.
- **Spec ID:** `SPEC-YYYY-MM-DD-<kebab-feature-name>`, the file name without `.md`.
- **Status:** `draft` → `approved` → `implemented` (`discovery` for a Discovery-First spec).
  Only Glib sets `approved`.
- **Language:** English, EARS acceptance criteria.
- **Tier:** picked with `engineering-paved-path:sdd-cascade`; the spec records the scorecard.
- **Boson facts:** a spec cites `docs/boson-protocol.md` by fact id (`F1`…) and never restates
  the fact.
- Specs are written by `sdd-engineering:spec-creator`. The spec commit lands before any code
  commit for that feature.

## Contents

(none yet)
