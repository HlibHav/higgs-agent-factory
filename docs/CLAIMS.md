# Claim register

Every number or factual claim we put on stage, in the IHBench PR or in the friction log has a
row here. No row, no claim. Protocol facts are cited by id from
[boson-protocol.md](boson-protocol.md).

Status: `ok` (evidence holds, phrasing approved) · `measure` (needs a run before use) ·
`conversation-only` (never on a slide or in writing) · `do-not-use`.

| claim | where used | evidence | honest phrasing | status |
|---|---|---|---|---|
| Higgs Realtime cost per minute | stage, Eval Card | F12 rates × audio minutes we measure client-side. Token cost cannot be measured (F2), and Realtime is billed by tokens (F12), so any figure is an estimate. | "Estimated audio cost from Boson's published per-minute rates: $X. Billed token cost: not measurable, the API returns no usage (F2)." | measure |
| Artificial Analysis τ-Voice 18.6%, TTFA 1.47 s | conversation only | https://artificialanalysis.ai/speech-to-speech, accessed 2026-10-24. The page shows no measurement date for Higgs Realtime. TTFA is on Big Bench Audio. | "Artificial Analysis lists Higgs Realtime at 18.6% on τ-Voice and 1.47 s TTFA, as of 2026-10-24." | conversation-only |
| Boson's pitch "Agents that coach themselves" | stage (framing) | https://www.boson.ai/, accessed 2026-10-24 | Quote it as Boson's line, with attribution. Our harness is one way to make it measurable. | ok |
| Boson reports IHBench-RQ 71.2 for Higgs Realtime | conversation only | https://www.boson.ai/blog/higgs-realtime, "our 2026-07-02 evaluation run" (self-run) | Never compare our IHBench number to it as marketing (non-goal in [BRIEF.md](BRIEF.md)). Frame the PR as "the public client for the benchmark Boson already reports on". | conversation-only |
