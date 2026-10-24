"""Step 23: the composition root and CLI, wired to the real session adapter + runner + card.

Offline: the Boson Realtime server is `fake_realtime_server`; TTS and judge are doubles.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from factory.__main__ import main
from factory.composition import ConfigError, FactoryApp, build_app
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore
from factory.gate.records import EvalCard, GateRunRecord
from factory.gate.runner import GateAborted
from factory.gate.tts_cache import TurnAudioSource
from factory.runtime.boson_session import BosonRealtimeSession
from tests.doubles import FakeJudge, FakeSessionFactory, FakeTts, Refuse
from tests.fake_realtime_server import close, delay, fake_realtime_server, send, wait_for

SECRET_BOSON = "boson-secret-value-123"
SECRET_ANTHROPIC = "anthropic-secret-value-456"
ENV = {"BOSON_API_KEY": SECRET_BOSON, "ANTHROPIC_API_KEY": SECRET_ANTHROPIC}


def _app(tmp_path: Path, sessions: Any, judge: Any | None = None) -> FactoryApp:
    return FactoryApp(
        sessions=sessions,
        audio=TurnAudioSource(FakeTts(), tmp_path / "tts", tmp_path / "recordings"),
        judge=judge or FakeJudge([]),
        store=FileCardStore(tmp_path / "cards"),
    )


def test_wire_quota_refused_card_incomplete(tmp_path: Path) -> None:
    error = {
        "type": "error",
        "error": {"type": "insufficient_quota", "message": "billing entitlement refused"},
    }
    script = [wait_for("session.update"), delay(50), send(error), close(4429)]

    async def main_() -> Any:
        async with fake_realtime_server(script) as (url, _):
            app = _app(tmp_path, lambda: BosonRealtimeSession(url=url, api_key="k"))
            return await asyncio.wait_for(app.run_gate_for_template("specialist-training"), 20)

    result = asyncio.run(main_())
    assert isinstance(result, EvalCard)
    assert result.verdict == "incomplete"
    assert result.incomplete_cause == "quota refused"
    stored = FileCardStore(tmp_path / "cards").latest("specialist-training")
    assert stored is not None and stored.run_id == result.run_id


def test_wire_refused_session_returns_aborted_and_stores_nothing(tmp_path: Path) -> None:
    factory = FakeSessionFactory([Refuse("voice not found")])
    app = _app(tmp_path, factory)
    result = asyncio.run(app.run_gate_for_template("specialist-training"))
    assert isinstance(result, GateAborted)
    assert "voice not found" in result.error_text
    assert not (tmp_path / "cards").exists()


def test_wire_unknown_template_is_aborted_without_a_session(tmp_path: Path) -> None:
    factory = FakeSessionFactory()
    result = asyncio.run(_app(tmp_path, factory).run_gate_for_template("nope"))
    assert isinstance(result, GateAborted)
    assert "nope" in result.error_text
    assert factory.calls == 0


@pytest.mark.parametrize("missing", ["BOSON_API_KEY", "ANTHROPIC_API_KEY"])
def test_config_missing_key_names_variable_not_value(missing: str, tmp_path: Path) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(ConfigError) as info:
        build_app(env, tmp_path)
    text = str(info.value)
    assert missing in text
    assert SECRET_BOSON not in text and SECRET_ANTHROPIC not in text


def test_config_blank_key_counts_as_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="BOSON_API_KEY"):
        build_app({**ENV, "BOSON_API_KEY": "  "}, tmp_path)


def test_build_app_makes_no_network_call(tmp_path: Path) -> None:
    app = build_app(ENV, tmp_path)
    assert isinstance(app, FactoryApp)
    asyncio.run(app.aclose())


def test_cli_missing_key_exits_nonzero_naming_variable(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(["gate", "--template", "specialist-training"], env={}, results_dir=tmp_path)
    err = capsys.readouterr().err
    assert code != 0
    assert "BOSON_API_KEY" in err


def test_cli_prints_card_and_path_and_exits_zero_for_incomplete(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class Stub:
        last_path = tmp_path / "cards" / "x.json"

        async def run_gate_for_template(self, template_id: str) -> EvalCard:
            return _incomplete_card()

        async def aclose(self) -> None:
            pass

    code = main(
        ["gate", "--template", "specialist-training"],
        env=ENV,
        results_dir=tmp_path,
        app_factory=lambda env, results: Stub(),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Verdict: incomplete" in out
    assert str(Stub.last_path) in out


def test_cli_aborted_prints_message_and_exits_nonzero(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class Stub:
        last_path = None

        async def run_gate_for_template(self, template_id: str) -> GateAborted:
            return GateAborted("the server refused the voice")

        async def aclose(self) -> None:
            pass

    code = main(
        ["gate", "--template", "specialist-training"],
        env=ENV,
        results_dir=tmp_path,
        app_factory=lambda env, results: Stub(),
    )
    captured = capsys.readouterr()
    assert code != 0
    assert "the server refused the voice" in captured.err
    assert "not released" in captured.err.lower()


def _incomplete_card() -> EvalCard:
    record = GateRunRecord(
        agent_id="specialist-training",
        run_id="20261024T000000Z-abcd1234",
        ended_at=datetime(2026, 10, 24, tzinfo=UTC),
        scenarios=[],
        turns=[],
        usages=[],
        input_audio_s=0.0,
        output_audio_s=0.0,
        cause="quota refused",
        cause_detail="billing entitlement refused",
    )
    return build_card(record)


def test_wire_judge_api_error_is_aborted_without_leaking_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anthropic
    import httpx

    async def boom(*args: Any, **kwargs: Any) -> Any:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.APIConnectionError(message=f"x-api-key {SECRET_ANTHROPIC}", request=request)

    monkeypatch.setattr("factory.composition.run_gate", boom)
    result = asyncio.run(
        _app(tmp_path, FakeSessionFactory()).run_gate_for_template("specialist-training")
    )
    assert isinstance(result, GateAborted)
    assert "APIConnectionError" in result.error_text
    assert SECRET_ANTHROPIC not in result.error_text
    assert not (tmp_path / "cards").exists()
