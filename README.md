# Higgs Agent Factory

Turn a one-line brief, or one of the five solution cards on [boson.ai/solutions](https://www.boson.ai/solutions), into a voice agent on Boson's Higgs Realtime API. The agent is a declarative Agent Spec, and it is only released after it passes an eval gate: scripted scenarios judged against a rubric, interruption recovery from IHBench, and client-side latency. The output is an Eval Card with measured numbers. Built for the Boson AI hackathon in Toronto, 2026-10-24.

## Quick start

```bash
uv sync
cp .env.example .env   # add BOSON_API_KEY and ANTHROPIC_API_KEY
uv run pytest -m "not live"
set -a; source .env; set +a
uv run python -m factory gate --template specialist-training   # live gate, prints the Eval Card
uv run python -m factory serve --port 8000                      # demo page on http://127.0.0.1:8000
```

The live gate and the demo page spend Boson and Anthropic credits (about a cent of audio per gate run). Use headphones for the live talk. Recording the demo: [docs/DEMO-RUNBOOK.md](docs/DEMO-RUNBOOK.md).

Where things stand: [STATUS.md](STATUS.md). How to work in this repo: [CLAUDE.md](CLAUDE.md). What and why: [docs/BRIEF.md](docs/BRIEF.md) and [specs/](specs/).
