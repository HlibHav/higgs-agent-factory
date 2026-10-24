"""Adapter half of the gate ACs: BosonRealtimeSession against the fake Realtime server.

Raw event dicts are passed in directly: the full `error` shape is UNVERIFIED (F13 names only
`type: "insufficient_quota"`), so the adapter must tolerate nested and flat variants.
"""

import asyncio
import base64
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from factory.agent_spec.models import AgentSpec
from factory.agent_spec.validation import validate_agent_spec
from factory.ports import (
    AudioDelta,
    OtherEvent,
    ResponseCreated,
    ResponseDone,
    SessionEnded,
    SessionEvent,
    SessionRefused,
    SpeechStarted,
    SpeechStopped,
    ToolCall,
    TranscriptDelta,
    Usage,
)
from factory.runtime.boson_session import BosonRealtimeSession
from tests.doubles import make_spec
from tests.fake_realtime_server import (
    Action,
    Received,
    audio_delta_event,
    close,
    delay,
    fake_realtime_server,
    idle_timeout_event,
    response_done_event,
    send,
    speech_started_event,
    speech_stopped_event,
    transcript_delta_event,
    usage_dict,
    wait_for,
)

TIMEOUT_S = 10.0


def _spec(**overrides: Any) -> AgentSpec:
    spec = validate_agent_spec(make_spec(**overrides))
    assert isinstance(spec, AgentSpec)
    return spec


_CLIENT_TOOL = {
    "kind": "client",
    "name": "lookup_policy",
    "description": "Look up a policy",
    "parameters": {"type": "object", "properties": {"id": {"type": "string"}}},
    "mock": {"default_output": '{"status": "active"}', "by_argument": []},
}


def _run(
    script: list[Action],
    body: Callable[[BosonRealtimeSession, list[Received]], Awaitable[Any]],
    *,
    spec: AgentSpec | None = None,
    auto_ack: bool = True,
    api_key: str | None = "test-key",
) -> Any:
    async def main() -> Any:
        async with fake_realtime_server(script, auto_ack=auto_ack) as (url, received):
            session = BosonRealtimeSession(url=url, api_key=api_key)
            try:
                return await asyncio.wait_for(body(session, received), TIMEOUT_S)
            finally:
                await session.close()

    return asyncio.run(main())


async def _collect(session: BosonRealtimeSession) -> list[SessionEvent]:
    return [event async for event in session.events()]


def _types(received: list[Received]) -> list[str]:
    return [r.event["type"] for r in received]


def test_spike_one_turn() -> None:
    script = [
        wait_for("input_audio_buffer.append"),
        send(audio_delta_event("r1", 4800)),
        close(1000),
    ]
    spec = _spec(
        temperature=0.5,
        max_output_tokens=200,
        turn_detection=None,
        tools=[_CLIENT_TOOL, {"kind": "server", "name": "web_search"}],
    )
    pcm = b"\x01\x00" * 480

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(spec)
        t_send = await session.send_audio(pcm)
        events = await _collect(session)
        return t_send, events, received

    t_send, events, received = _run(script, body)

    update = received[0].event
    assert update["type"] == "session.update"  # F1
    cfg = update["session"]
    assert cfg["instructions"] == spec.instructions
    assert cfg["output_modalities"] == ["audio"]  # F6
    assert cfg["audio"]["output"]["voice"] == "default"
    assert cfg["audio"]["input"]["turn_detection"] is None  # F24
    assert cfg["temperature"] == 0.5
    assert cfg["max_output_tokens"] == 200
    tool_types = sorted(t["type"] for t in cfg["tools"])
    assert tool_types == ["function", "web_search"]  # F10

    append = next(r for r in received if r.event["type"] == "input_audio_buffer.append")
    assert base64.b64decode(append.event["audio"]) == pcm  # F4
    assert t_send <= append.t

    delta = next(e for e in events if isinstance(e, AudioDelta))
    assert delta == AudioDelta(response_id="r1", nbytes=4800, t=delta.t)
    assert delta.t >= t_send
    assert isinstance(events[-1], SessionEnded)


def test_server_vad_is_sent_when_spec_has_it() -> None:
    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return received[0].event["session"]["audio"]["input"]["turn_detection"]

    td = _run([wait_for("session.update"), delay(50), close(1000)], body)
    assert td["type"] == "server_vad"  # F24
    assert td["threshold"] == 0.85  # F8
    assert td["prefix_padding_ms"] == 300
    assert td["silence_duration_ms"] == 500


def test_ac14_4429_maps_quota_refused() -> None:
    # F13: error type insufficient_quota, then close 4429. Nested error shape is a guess.
    error = {
        "type": "error",
        "error": {"type": "insufficient_quota", "message": "billing entitlement refused"},
    }
    script = [wait_for("session.update"), delay(50), send(error), close(4429)]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    events = _run(script, body)
    ended = [e for e in events if isinstance(e, SessionEnded)]
    assert len(ended) == 1
    assert ended[0].cause == "quota refused"
    assert "billing entitlement refused" in (ended[0].error_text or "")


def test_ac14_close_4429_alone_maps_quota_refused() -> None:
    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    events = _run([wait_for("session.update"), delay(50), close(4429)], body)
    assert events[-1] == SessionEnded("quota refused", 4429, None, events[-1].t)


def test_ac14_flat_error_shape_is_tolerated() -> None:
    error = {"type": "insufficient_quota", "message": "no credit"}
    flat = {"type": "error", **error}
    script = [wait_for("session.update"), delay(50), send(flat), close(4429)]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    ended = [e for e in _run(script, body) if isinstance(e, SessionEnded)]
    assert [e.cause for e in ended] == ["quota refused"]


def test_ac15_idle_timeout_cause() -> None:
    script = [wait_for("session.update"), delay(50), send(idle_timeout_event()), close(1000)]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    ended = [e for e in _run(script, body) if isinstance(e, SessionEnded)]
    assert len(ended) == 1
    assert ended[0].cause == "idle timeout"  # F8


def test_ac16_1013_concurrency_limit() -> None:
    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    events = _run([wait_for("session.update"), delay(50), close(1013)], body)
    assert events[-1] == SessionEnded("concurrency limit", 1013, None, events[-1].t)  # F21


def test_other_close_code_is_closed_with_code() -> None:
    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    events = _run([wait_for("session.update"), delay(50), close(3000)], body)  # F13: bad key
    assert events[-1] == SessionEnded("closed", 3000, None, events[-1].t)


def test_ac20_refused_voice_raises_with_text() -> None:
    # F7, F14: the first session.update is answered with an error instead of session.created.
    error = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "unknown voice: nope"},
    }
    script = [wait_for("session.update"), send(error), close(1008)]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        with pytest.raises(SessionRefused) as info:
            await session.open(_spec(voice="nope"))
        return info.value

    refused = _run(script, body, auto_ack=False)
    assert "unknown voice: nope" in refused.error_text
    assert "test-key" not in refused.error_text


def test_ac20_close_before_created_raises_refused() -> None:
    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        with pytest.raises(SessionRefused):
            await session.open(_spec())

    _run([wait_for("session.update"), close(1008)], body, auto_ack=False)


def test_ac21_server_web_search_no_reply() -> None:
    # F10: server tool = function_call item with executor "server"; the client sends nothing.
    item = {
        "type": "function_call",
        "id": "item-ws",
        "call_id": "call-ws",
        "name": "web_search",
        "arguments": '{"query": "ihbench"}',
        "executor": "server",
    }
    added = {"type": "response.output_item.added", "response_id": "r1", "output_index": 0}
    script = [
        wait_for("session.update"),
        delay(50),
        send({**added, "item": item}),
        send(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call-ws",
                "arguments": '{"query": "ihbench"}',
            }
        ),
        send({"type": "response.output_item.done", "response_id": "r1", "item": item}),
        delay(100),
        close(1000),
    ]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        events = await _collect(session)
        return events, received

    events, received = _run(script, body)
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(calls) == 1
    assert calls[0].executor == "server"
    assert calls[0].name == "web_search"
    assert _types(received) == ["session.update"]  # no output, no response.create


def test_ac22_tool_output_sent() -> None:
    # F10/F3: client call surfaces once arguments are done; the output is one item.create.
    item = {
        "type": "function_call",
        "id": "item-1",
        "call_id": "call-1",
        "name": "lookup_policy",
        "arguments": "",
        "executor": "client",
    }
    script = [
        wait_for("session.update"),
        delay(50),
        send(
            {
                "type": "response.output_item.added",
                "response_id": "r1",
                "output_index": 0,
                "item": item,
            }
        ),
        send(
            {
                "type": "response.function_call_arguments.done",
                "response_id": "r1",
                "item_id": "item-1",
                "call_id": "call-1",
                "name": "lookup_policy",
                "arguments": '{"id": "P-1"}',
            }
        ),
        send(
            {
                "type": "response.output_item.done",
                "response_id": "r1",
                "item": {**item, "arguments": '{"id": "P-1"}'},
            }
        ),
        wait_for("conversation.item.create"),
        delay(150),
        close(1000),
    ]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec(tools=[_CLIENT_TOOL]))
        events: list[SessionEvent] = []
        async for event in session.events():
            events.append(event)
            if isinstance(event, ToolCall):
                await session.send_tool_output(event.call_id, '{"status": "active"}')
        return events, received

    events, received = _run(script, body)
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert len(calls) == 1
    assert (calls[0].call_id, calls[0].name, calls[0].executor) == (
        "call-1",
        "lookup_policy",
        "client",
    )
    assert calls[0].arguments == {"id": "P-1"}
    assert _types(received) == ["session.update", "conversation.item.create"]
    created = received[1].event["item"]
    assert created["type"] == "function_call_output"
    assert created["call_id"] == "call-1"
    assert created["output"] == '{"status": "active"}'


def test_usage_and_transcript_mapping() -> None:
    script = [
        wait_for("session.update"),
        delay(50),
        send(speech_started_event(10)),
        send(speech_stopped_event(900)),
        send(transcript_delta_event("r1", "Hello")),
        send(response_done_event("r1", usage=usage_dict(22, 3, 0))),
        send(response_done_event("r2", status="cancelled", usage=None)),
        send(response_done_event("r3", usage={**usage_dict(1, 2), "input_tokens": "many"})),
        send({"type": "conversation.context.summarized", "event_id": "x"}),
        delay(50),
        close(1000),
    ]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    events = _run(script, body)
    kinds = [type(e) for e in events]
    assert kinds == [
        SpeechStarted,
        SpeechStopped,
        TranscriptDelta,
        ResponseDone,
        ResponseDone,
        ResponseDone,
        OtherEvent,
        SessionEnded,
    ]
    assert events[2].response_id == "r1" and events[2].text == "Hello"  # F18
    assert events[3].usage == Usage(22, 0, 3)  # F2: input 22, cached 0, output 3
    assert events[3].status == "completed"
    assert events[4].usage is None and events[4].status == "cancelled"
    assert events[5].usage is None  # non-numeric count
    assert events[6].type == "conversation.context.summarized"  # F5: tolerate unknown
    assert all(a.t <= b.t for a, b in zip(events, events[1:], strict=False))


def test_timestamps_use_injected_clock() -> None:
    ticks = iter(range(100, 10_000))

    async def main() -> list[SessionEvent]:
        script = [
            wait_for("session.update"),
            delay(50),
            send(speech_started_event()),
            delay(50),
            close(1000),
        ]
        async with fake_realtime_server(script) as (url, _):
            session = BosonRealtimeSession(url=url, api_key=None, clock=lambda: float(next(ticks)))
            try:
                await session.open(_spec())
                return await asyncio.wait_for(_collect(session), TIMEOUT_S)
            finally:
                await session.close()

    events = asyncio.run(main())
    assert all(float(e.t).is_integer() and e.t >= 100 for e in events)


def test_response_created_maps_to_event() -> None:
    created = {
        "event_id": "fake-created-r1",
        "type": "response.created",
        "response": {"id": "r1", "object": "realtime.response", "status": "in_progress"},
        "metadata": None,
    }
    script = [wait_for("session.update"), delay(50), send(created), delay(50), close(1000)]

    async def body(session: BosonRealtimeSession, received: list[Received]) -> Any:
        await session.open(_spec())
        return await _collect(session)

    events = _run(script, body)
    assert isinstance(events[0], ResponseCreated)  # F17
    assert events[0].response_id == "r1"
    assert isinstance(events[0].t, float)
