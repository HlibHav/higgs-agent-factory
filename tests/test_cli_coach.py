import json
from pathlib import Path
from typing import Any

import pytest

from factory.__main__ import main
from tests.doubles import FakeTts, make_spec
from tests.test_gate_runner import GOOD, Harness, reply


class _App:
    def __init__(self, pair: Any = None) -> None:
        self.pair = pair
        self.kwargs: dict[str, Any] = {}

    async def coach_template(self, template_id: str, **kw: Any) -> Any:
        self.kwargs = {"template": template_id, **kw}
        from factory.gate.runner import GateAborted

        return GateAborted("stop here")

    def coach_pair(self, agent_id: str) -> Any:
        return self.pair

    async def aclose(self) -> None:
        return None


def test_coach_cli_passes_options_and_exits_2_on_abort(tmp_path: Path) -> None:
    app = _App()
    code = main(
        [
            "coach",
            "--template",
            "specialist-training",
            "--rounds",
            "1",
            "--fresh",
            "--caller-voice",
            "jake",
        ],
        results_dir=tmp_path,
        app_factory=lambda env, results: app,
    )
    assert code == 2
    assert app.kwargs == {
        "template": "specialist-training",
        "rounds": 1,
        "from_latest": False,
        "caller_voice": "jake",
    }


def test_diff_cli_without_pair_exits_2(tmp_path: Path) -> None:
    code = main(["diff", "x"], results_dir=tmp_path, app_factory=lambda e, r: _App())
    assert code == 2


def test_caller_voice_rejects_unknown_voice(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["gate", "--template", "specialist-training", "--caller-voice", "zed"])


def test_ac80_caller_voice_overrides_every_scripted_turn(tmp_path: Path) -> None:
    import asyncio

    from factory.gate.runner import run_gate

    tts = FakeTts()
    h = Harness(tmp_path, make_spec(), reply(), [GOOD], tts=tts)
    asyncio.run(
        run_gate(
            h.spec,
            sessions=h.factory,
            audio=h.audio,
            judge=h.judge,
            sleep=h.sleep,
            caller_voice="marcus",
        )
    )
    assert tts.requests and {v for _, v in tts.requests} == {"marcus"}
    assert json.dumps(h.spec.scenarios[0].user_voice) == '"chloe"'
