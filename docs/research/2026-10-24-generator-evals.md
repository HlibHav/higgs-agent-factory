# Evaluating the brief → Agent Spec generator

Date: 2026-10-24. Type: research gate, fast (research-tools:researcher, existing NotebookLM
notebooks `36cedf6b-8559-4cff-a380-d5dd67e9689b` and `8013b38c-4598-415f-ab06-fee3f8f028f7`,
plus web checks). Status: research only; nothing below is implemented yet.

## The problem

Nobody checks the generator. One Sonnet call turns a ≤1,000-character brief into a schema-2
Agent Spec (persona, skills with procedures, mocked tools, scenarios with rubrics), and the gate
then judges the agent that spec produces. If the generator writes weak rubrics, the gate will
happily release a weak agent.

## What the sources say

No published benchmark targets "an LLM that writes agent specs". The workable approach is to
combine pieces that are established:

- **Grader pyramid.** Use code checks first, a model judge only for what code cannot decide,
  and humans to calibrate the judge. Grade each dimension in its own isolated judge call, give
  the judge an "unknown" exit, and read transcripts of many trials. Keep regression evals
  (should stay near 100%) separate from capability evals. Use pass^k ("all k trials succeed")
  for consistency. Anthropic, *Demystifying evals for AI agents*,
  https://anthropic.com/engineering/demystifying-evals-for-ai-agents (2026-01-09).
- **Calibrate the judge against humans before scaling it.** Watch position and verbosity bias
  and control for length. OpenAI, *Evaluation best practices*,
  https://developers.openai.com/api/docs/guides/evaluation-best-practices. The same page says
  the hosted OpenAI Evals platform is being retired (read-only 2026-10-31), so use the
  guidance, not the platform.
- **Judge bias is systematic, not just noise.** Position, verbosity and self-enhancement bias
  (MT-Bench, https://arxiv.org/abs/2306.05685). Position consistency and repetition stability
  as metrics (https://arxiv.org/abs/2406.07791). A panel of judges from different model
  families beats one big judge and costs less (PoLL, https://arxiv.org/abs/2404.18796). Twelve
  bias types are catalogued in CALM (https://arxiv.org/abs/2410.02736). Our judge and our
  generator are both Sonnet, so self-preference is a real risk here (inference).
- **Frameworks to borrow shapes from**: Inspect `model_graded_qa` with per-sample criteria and
  stderr (https://inspect.aisi.org.uk/model-graded.html); promptfoo `llm-rubric` and red-team
  plugins (https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded,
  https://promptfoo.dev/docs/red-team/configuration); DeepEval G-Eval/DAG
  (https://www.deepeval.com/docs/metrics-llm-evals); LangSmith experiments compared against a
  baseline (https://docs.langchain.com/langsmith/evaluation-concepts).
- **Prompt optimizers live and die by their metric.** OPRO (https://arxiv.org/abs/2309.03409)
  and DSPy MIPROv2 (https://dspy.ai/api/optimizers/MIPROv2/) optimize whatever you score. Our
  coach loop is a small optimizer of the same kind, so a gameable judge would get optimized into
  verbosity.
- **Adversarial inputs**: InjecAgent (https://arxiv.org/abs/2403.02691) and AgentDojo
  (https://arxiv.org/abs/2406.13352) grade injections by checking state in code, not with a
  judge. For us that means checking the generated spec's structure.

## Recommended minimal plan for this repo

1. **Golden briefs, frozen in the repo (4–5):**
   - a single-skill baseline;
   - a multi-skill brief with two or more tools that need mocks;
   - an underspecified brief;
   - an adversarial brief (asks for server `web_search`, an outbound-URL tool, or "print your
     system prompt");
   - optionally, a brief at the 1,000-character limit.

   Each one carries 5–10 "requirement atoms" the spec must cover, not a full reference spec.
2. **Layer A: offline, every commit.**
   - The spec validates as schema 2.
   - Budget caps hold.
   - Every client tool has a mock.
   - There are no server tools and no recordings.
   - Every scenario has all three rubric lists.
   - A lexical check that each requirement atom appears somewhere.
3. **Layer B: judged, on demand.** One isolated judge call per dimension: brief coverage,
   rubric decidability (F27), procedure faithfulness and mock realism. Each call runs k = 2,
   with disagreement counted as "unknown", the same rule as the gate (AC-75). Before trusting
   it, calibrate on 10–20 hand-labelled pairs and report agreement and Cohen's kappa.
4. **Layer C: the headline.** Generate n = 3 specs per golden brief, run each through the voice
   gate, and report counts, for example "9/12 specs valid, 7/12 released". Add one hand-written
   control spec, so gate flakiness is not blamed on the generator.
5. **Layer D: adversarial, pass/fail in code.** No deny-listed tool or field, the caps hold, and
   no brief text in a privileged field.
6. **Regression ledger.** Key results by a hash of the generator prompt plus the model id, and
   compare each new prompt version against the baseline brief by brief.

Every number shown on stage still needs a `docs/CLAIMS.md` row.

## Not verified

- Kappa thresholds (0.6 / 0.8) come from notebook answers, not primary sources.
- The MT-Bench agreement figures were seen only in search summaries.
- The APE paper (arXiv 2211.01910) was not retrieved.
- The framework docs were read through search summaries.
- The size of the Sonnet-judging-Sonnet effect in this setup is unmeasured.
