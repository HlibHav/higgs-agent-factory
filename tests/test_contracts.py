"""Lane 0 contracts: importability, the Realtime fake server and the test doubles."""

import asyncio
import json

import websockets

from tests.doubles import (
    FakeBriefModel,
    FakeJudge,
    FakeSessionFactory,
    FakeTts,
    make_spec,
)
from tests.fake_realtime_server import close, delay, fake_realtime_server, send, wait_for


def test_factory_importable() -> None:
    import factory.agent_spec.models
    import factory.gate.records
    import factory.ports

    assert factory.ports.SessionRefused
    assert factory.gate.records.EvalCard
    assert factory.agent_spec.models.AgentSpec


def test_fake_server_records_and_closes() -> None:
    async def scenario() -> tuple[int | None, list[dict]]:
        script = [wait_for("session.update"), delay(10), close(4429)]
        async with fake_realtime_server(script) as (url, received):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"type": "session.update", "session": {}}))
                first = json.loads(await ws.recv())  # F1/F14: first update -> session.created
                assert first["type"] == "session.created"
                try:
                    await ws.recv()
                except websockets.ConnectionClosed:
                    pass
                code = ws.close_code
            return code, list(received)

    code, received = asyncio.run(scenario())
    assert code == 4429
    assert [r.event["type"] for r in received] == ["session.update"]
    assert isinstance(received[0].t, float)


def test_fake_server_sends_scripted_events_in_order() -> None:
    async def scenario() -> list[str]:
        script = [
            wait_for("input_audio_buffer.append"),
            send({"type": "response.output_audio.delta", "response_id": "r1", "delta": "AAAA"}),
            send({"type": "session.idle_timeout"}),
            close(1000),
        ]
        async with fake_realtime_server(script) as (url, _received):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"type": "session.update", "session": {}}))
                types: list[str] = []
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": "AAAA"}))
                try:
                    async for raw in ws:
                        types.append(json.loads(raw)["type"])
                except websockets.ConnectionClosed:
                    pass
                return types

    assert asyncio.run(scenario()) == [
        "session.created",
        "response.output_audio.delta",
        "session.idle_timeout",
    ]


def test_make_spec_is_valid_and_overridable() -> None:
    from factory.agent_spec.models import AgentSpec
    from factory.agent_spec.validation import validate_agent_spec

    assert isinstance(validate_agent_spec(make_spec()), AgentSpec)
    assert make_spec(role="x")["role"] == "x"


def test_fake_session_counts_and_records_sends() -> None:
    from factory.agent_spec.models import AgentSpec
    from factory.agent_spec.validation import validate_agent_spec
    from factory.ports import AudioDelta

    spec = validate_agent_spec(make_spec())
    assert isinstance(spec, AgentSpec)
    factory = FakeSessionFactory([AudioDelta("r1", 480, 1.0)])

    async def scenario() -> list:
        session = factory()
        await session.open(spec)
        await session.send_audio(b"\x00" * 4800)
        await session.send_tool_output("c1", "ok")
        got = [event async for event in session.events()]
        await session.close()
        return got

    got = asyncio.run(scenario())
    assert factory.calls == 1
    session = factory.sessions[0]
    assert session.open_calls == 1
    assert [s.kind for s in session.sends] == ["audio", "tool_output"]
    assert got == [AudioDelta("r1", 480, 1.0)]


def test_other_doubles_count_calls() -> None:
    tts = FakeTts(fail_texts={"bad"})
    judge = FakeJudge(["{}"])
    brief = FakeBriefModel("{}")

    async def scenario() -> None:
        assert await tts.synthesise("hi", "chloe")
        try:
            await tts.synthesise("bad", "chloe")
        except Exception as exc:  # noqa: BLE001
            assert type(exc).__name__ == "TtsError"
        assert await brief.draft_spec("b") == "{}"

    asyncio.run(scenario())
    assert tts.requests == [("hi", "chloe"), ("bad", "chloe")]
    assert brief.calls == 1
    assert judge.requests == []
