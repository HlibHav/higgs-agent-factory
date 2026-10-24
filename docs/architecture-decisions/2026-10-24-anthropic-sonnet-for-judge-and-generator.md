---
status: accepted
date: 2026-10-24
decision-makers: [Glib]
scope: backend
---

# Use Anthropic claude-sonnet-5-5 for the scenario judge and the free-brief generator

## Context and Problem Statement
The eval gate (spec `specs/2026-10-24-higgs-agent-factory.md`) needs an LLM judge that labels each scenario PASS / PARTIAL / FAIL with a rationale and evidence, and an optional generator that turns a free-text brief into an Agent Spec. The judge vendor was set to Anthropic earlier the same day (`ANTHROPIC_API_KEY` in `.env.example`). A gate run makes about six judge calls, and one scenario runs live on stage, so latency is visible.

## Considered Options
- `claude-sonnet-5-5` for both.
- `claude-opus-5-5` for both.
- `claude-haiku-5-5` for both.

## Decision Outcome
Chosen option: `claude-sonnet-5-5` for both roles, because it balances rubric-judging quality against the latency of the one live scenario, and one model and one SDK keep the adapters simple. The template path (Specialist Training) stays deterministic and makes no model call; the free-brief generator is a cuttable plan step (6b).

### Consequences
- Good: one key, one SDK, one model to reason about; faster than Opus on stage.
- Bad: weaker judgement than Opus on borderline PARTIAL cases; cost per call is not yet recorded here and must come from a cited source or a measured run (`docs/CLAIMS.md`), not memory.

### Confirmation
The judge and generator adapters read the model id from the composition root (`FACTORY_JUDGE_MODEL`); the plan's adapter tests pin that the configured id is sent. Any change of model is a superseding record.

## More Information
Plan: `docs/plans/2026-10-24-higgs-agent-factory.md` (open questions, judge and generator). Glib's answers in chat, 2026-10-24.
