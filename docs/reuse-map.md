# Reuse map: what we do not build

Boson already ships most of the pieces. We reuse them and spend our hours on the eval gate.
Protocol facts are cited by id from [boson-protocol.md](boson-protocol.md).

| piece | license | what we use | how we consume it | what we must not rebuild |
|---|---|---|---|---|
| [`boson-ai/pipecat-boson`](https://github.com/boson-ai/pipecat-boson) | BSD-2-Clause (`LICENSE`, © 2026 Boson AI) | The agent runtime: `BosonRealtimeLLMService`, a Pipecat speech-to-speech service with `instructions`, `voice`, `tools`, `turn_detection`, `output_modalities` | Dependency, `uv add pipecat-boson` (PyPI 0.1.4, requires Python ≥ 3.11), added by the plan's runtime lane, not in the scaffold | A Realtime WebSocket client, our own S2S loop, tool dispatch, barge-in handling. Do not fork it. |
| [`boson-ai/ihbench`](https://github.com/boson-ai/ihbench) | Apache-2.0 (© 2026 Boson AI; paper authors include Boson's founders) | The interruption-recovery eval: samples, runner, RQ (recovery quality) rubric judge | Our client lives in the fork `../ihbench-higgs`, branch `feat/higgs-realtime-client`, contributed back as a PR. This repo reads its `responses/*.jsonl` and judge output. | The benchmark, its dataset or its judge. |
| [`boson-ai/ProactBench`](https://github.com/boson-ai/ProactBench) | Apache-2.0 | The rubric shape for our scenario tests: verdict labels `PASS / PARTIAL / FAIL` with `pass_criteria`, `partial_criteria`, `fail_criteria`, and a judge that returns `score`, `rationale`, `evidence` (a verbatim quote) | Copy the shape into the Agent Spec contract. The weights 1 / 0.5 / 0 are ours; ProactBench tallies labels and has no numeric weights (`proactbench/types.py:19`). | Its runner. It is text-only ("Audio, vision, and streaming are out of scope", `proactbench/clients.py:23`). |
| [Avatar realtime-sessions recipe](https://docs.boson.ai/models/higgs-avatar/realtime-sessions) | Boson docs | P3 only: the four-participant LiveKit room (user, our agent, the room, the Boson avatar) | Follow the documented pattern and F11 | Our own lip-sync or video pipeline. |
| [Voices API](https://docs.boson.ai/api-reference/audio/create-a-voice) | Boson API | Persona voices: `POST /v1/audio/voices`, then `voice_<id>` in the session (F7) | HTTP call at agent-generation time | Voice cloning. |
| `boson-ai/lina-voice-agent` | Listed as MIT (Aug 2026) | Nothing yet | — | — |
| Feynman Flow | Unknown | Nothing | — | Anything that competes with it. We are a community layer on the public API. |

## ihbench: how our client fits

The README's "Adding a model" pattern ("two files and zero edits to the runner") covers local
Hugging Face models only: `@register_client` is typed to `LocalClient` and matched against HF
model ids (`ihbench/clients/registry.py:24`). API backends are a fixed list in `make_client`
(`scripts/run_inference_api.py:38-68`), and `OpenAIRealtimeClient` takes no `base_url`.

Decision (Glib, 2026-10-24): the PR adds `ihbench/clients/higgs_realtime_client.py`,
`configs/higgs-realtime.yaml`, and about six runner lines (one `--backend` choice and one
`make_client` branch). The existing OpenAI realtime client cannot run against Higgs because of
F1, F3 and F5 (`openai_realtime_client.py:97-99`, `:65-68`, `:80`, `:125-130`). Spec:
`specs/2026-10-24-ihbench-higgs-client.md`.

## pipecat-boson provenance check

Boson's Pipecat page says to install from GitHub during the preview. On 2026-10-24 the PyPI
sdist `pipecat-boson==0.1.4` was downloaded and its `pipecat_boson/` tree diffed against the
GitHub clone: `diff -rq` reported no differences. PyPI metadata names no author, so if a later
version appears, diff it again before upgrading.

## Open questions

- **`lina-voice-agent`.** `git ls-remote` returns "Repository not found", so it is private or
  gone. Ask Boson engineers on site whether it is their reference agent. Do not guess what it
  contains.
- **Feynman Flow.** Mentioned only on [boson.ai/about](https://www.boson.ai/about) as "an
  agentic platform". Ask on site what it is and whether a public API is planned.
