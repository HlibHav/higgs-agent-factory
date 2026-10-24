"""Step 24 (AC-45): the live end-to-end gate. Run by the main session, never by a lane.

`uv run pytest -m live tests/test_e2e_gate.py` needs BOSON_API_KEY and ANTHROPIC_API_KEY in the
environment; it opens one real Boson Realtime session, calls Boson TTS and the Anthropic judge,
and spends credits.
"""

import asyncio
import os
from pathlib import Path

import pytest

from factory.composition import build_app
from factory.gate.records import EvalCard


@pytest.mark.live
def test_ac45_specialist_training_live(tmp_path: Path) -> None:
    app = build_app(os.environ, Path("results"))

    async def run() -> object:
        try:
            return await app.run_gate_for_template("specialist-training")
        finally:
            await app.aclose()

    card = asyncio.run(run())
    assert isinstance(card, EvalCard), f"gate did not produce a card: {card}"
    assert card.verdict
    assert card.ttfa_n >= 1
    assert card.input_audio_minutes > 0
    assert card.output_audio_minutes > 0
    assert card.estimated_audio_cost_usd is not None
