> **Priority.** This repo's conventions win over global rules (`~/.claude`) inside this repo.
> Where this file is silent, the global rules apply.

# Higgs Agent Factory — agent guide

A harness that turns a brief into a voice agent on Boson's Higgs Realtime API, gates it on
evals, and prints an Eval Card. Goal, audience and priorities: `docs/BRIEF.md`. Current state:
`STATUS.md` (the only place that holds it).

## Hard rule: Boson API facts

Any statement about Boson API behaviour must cite `docs/boson-protocol.md`. If the fact is not
there, it is UNVERIFIED: write a live test or ask. Never infer from the OpenAI Realtime API.

The same holds for numbers: every number shown on stage, in a PR or in the friction log has a
row in `docs/CLAIMS.md` that points at a measured run or a cited source.

## Before answering

Read in this order, and stop as soon as the task is answered:

1. `STATUS.md` — what works, what is blocked, what is next.
2. This file.
3. The touched package's `INSIGHTS.md` (`factory/INSIGHTS.md`), through the
   `engineering-paved-path:engineering-insights` skill.
4. `docs/boson-protocol.md` for anything that touches the Boson API.
5. The active spec in `specs/` and its plan in `docs/plans/`.

Then code. `vendor-ref/` is reference reading for Boson's public repos, never a source to
import from.

## Stack

| Area | Choice |
|---|---|
| Language | Python 3.12 |
| Package manager | `uv` (`pyproject.toml`, `uv.lock`) |
| Tests | `pytest`; the `live` marker means the test hits the Boson API and spends credits |
| Lint and format | `ruff` |
| Agent runtime | `pipecat-boson` (BSD-2), consumed as a dependency once the plan adds it; see `docs/reuse-map.md` |
| Interruption eval | IHBench, through our client in the fork `../ihbench-higgs` (not this repo) |

## Run

```bash
uv sync                                  # install the locked environment
uv run python scripts/smoke.py           # live Realtime smoke check, < $0.01, needs .env
uv run pytest -m live scripts/smoke.py   # the same check through pytest
```

Secrets come from `.env` (template: `.env.example`). Never print a key; check presence with
`[ -n "$BOSON_API_KEY" ] && echo OK`.

## Check

| Check | Command | Network |
|---|---|---|
| Offline tests | `uv run pytest -m "not live"` | none |
| Lint | `uv run ruff check` | none |
| Format | `uv run ruff format --check` | none |
| IHBench client offline tests (fork, test branch) | `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` | none |
| IHBench client offline tests on websockets 12.0 (AC-38) | `/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/.venv-ws12/bin/python -m pytest /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs/tests/test_higgs_realtime_client.py` | none |
| IHBench PR footprint (AC-26, main session only: the guard denies `git -C`) | `git -C /Users/Glebazzz/Claude/PROJECTS/ihbench-higgs diff --name-only upstream/main...feat/higgs-realtime-client` | none, not in guard |
| Live smoke | `uv run pytest -m live scripts/smoke.py` | Boson API, spends credits |

`.claude/agent-guard.json` lists exactly the commands with no network, so read-only agents
never spend API credits. `tests/test_scaffold.py` fails if the two lists drift apart.

"Done" follows `engineering-paved-path:verify-done`: the command plus its quoted result line.
A claim from reading a diff is not done.

## Naming conventions

- Specs: `specs/YYYY-MM-DD-<feature>.md`, English, EARS acceptance criteria, status
  `draft → approved → implemented`, a `## Changelog`. Only Glib sets `approved`.
- Plans: `docs/plans/YYYY-MM-DD-<feature>.md`, with `.state.md` and `.verify.md` beside them,
  written by `sdd-engineering:implementation-planner` and `/sdd-engineering:run-plan`.
- Python: modules and files in `snake_case`, tests as `tests/test_<area>.py`, live tests
  carry `@pytest.mark.live`.
- Protocol facts: `F<n>` ids in `docs/boson-protocol.md`, tagged `VERIFIED-DOCS (date)` or
  `VERIFIED-RUN (date)`. Only a live run upgrades a tag.
- Branches: `feat/…`, `fix/…`, `chore/…`, `docs/…`. Commits: conventional (`feat:`,
  `docs:`, `chore:`), and the spec commit lands before any code commit for that feature.

## Do-not-touch

- `vendor-ref/` — shallow clones of Boson repos, git-ignored and read-only. Never edit, never
  import from it.
- `uv.lock` — change it only through `uv add` / `uv remove` / `uv lock`.
- `.env` — never read it into output, never commit it.

## Use when

- How much spec a change needs, and where it lives → `engineering-paved-path:sdd-cascade`.
- Writing or updating a spec → `sdd-engineering:spec-creator` (the main session relays its
  questions and research requests).
- A spec is approved and needs a plan → `sdd-engineering:implementation-planner`.
- A saved plan should be executed → `/sdd-engineering:run-plan docs/plans/<plan>.md`.
- A question the repo or the web can answer with evidence → `research-tools:researcher`.
- Reviewing a diff against layer boundaries → `architecture-review:architecture-reviewer`.
- About to say done, fixed or ready → `engineering-paved-path:verify-done`.
- Starting or finishing work in `factory/` → `engineering-paved-path:engineering-insights`.
- Starting a session → `/start`. Ending one → `/wrap`.
