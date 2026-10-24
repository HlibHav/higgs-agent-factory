# Claim register

Every number or factual claim we put on stage, in the IHBench PR or in the friction log has a
row here. No row, no claim. Protocol facts are cited by id from
[boson-protocol.md](boson-protocol.md).

Status: `ok` (evidence holds, phrasing approved) · `measure` (needs a run before use) ·
`conversation-only` (never on a slide or in writing) · `do-not-use`.

| claim | where used | evidence | honest phrasing | status |
|---|---|---|---|---|
| Higgs Realtime cost per minute | stage, Eval Card | Token cost = `usage` from `response.done` × F12 token rates, when every response in the run reported `usage` (seen on a text-mode response, F2; audio mode not yet observed). Separately, F12 per-minute rates × audio minutes we measure client-side, labelled as Boson's estimate. | "Token cost from reported usage: $X per minute." If any response lacked usage: "Billed token cost: not measurable, the API returns no usage (F2)." (verbatim in spec AC-31). Always alongside: "Estimated audio cost from Boson's published per-minute rates: $Y." | measure |
| Eval Card TTFA p50/p95 | stage, Eval Card | Client-side, from the end of the scripted user audio to the first `response.output_audio.delta` (F17), per Spec A. Includes the server VAD silence window (F8). | "TTFA p50 X s / p95 Y s, measured client-side from end of user audio, N turns, run <id>." Never next to the Artificial Analysis 1.47 s. | measure |
| Live-session TTFA | stage (demo page) | Client-side, from `speech_stopped` (F15) to the first audio delta. Not comparable with the Eval Card TTFA. | "Live TTFA X s, from end of detected speech." Labelled with its start point. | measure |
| Barge-in stop time | stage, Eval Card | Client-side, from the first interrupting audio chunk sent to the last assistant audio chunk received (F15, F17), per Spec A. | "Assistant audio stopped X ms after the interruption began, client-side, N interruptions." | measure |
| Artificial Analysis τ-Voice 18.6%, TTFA 1.47 s | conversation only | https://artificialanalysis.ai/speech-to-speech, accessed 2026-10-24. The page shows no measurement date for Higgs Realtime. TTFA is on Big Bench Audio. | "Artificial Analysis lists Higgs Realtime at 18.6% on τ-Voice and 1.47 s TTFA, as of 2026-10-24." | conversation-only |
| Boson's pitch "Agents that coach themselves" | stage (framing) | https://www.boson.ai/, accessed 2026-10-24 | Quote it as Boson's line, with attribution. Our harness is one way to make it measurable. | ok |
| Boson reports IHBench-RQ 71.2 for Higgs Realtime | conversation only | https://www.boson.ai/blog/higgs-realtime, "our 2026-07-02 evaluation run" (self-run) | Never compare our IHBench number to it as marketing (non-goal in [BRIEF.md](BRIEF.md)). Frame the PR as "the public client for the benchmark Boson already reports on". | conversation-only |
