"""Adapter: `RealtimeSession` over pipecat-boson, tapped for raw wire events.

pipecat-boson 0.1.4 hides what the gate measures: it sends its own `response.cancel` on
barge-in, drops later deltas of a cancelled response, and shows 4429 / 1013 only as an error
string. `_TappedService` therefore wraps three of its private methods (pin `==0.1.4`):
`_dispatch_boson_server_event` (every inbound event, before pipecat filters it),
`_ws_send` (every outbound event) and `_mark_websocket_disconnected` (reads the close code).
Those become our domain events from `factory.ports`.

The service runs outside a Pipecat pipeline: we call `setup` and send a `StartFrame`
ourselves, and never push frames into it. The API key travels only in the F23 header that
pipecat-boson builds; this module never logs it.
"""

import asyncio
import base64
import binascii
import json
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import EndFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessorSetup
from pipecat.utils.asyncio.task_manager import TaskManager
from pipecat_boson.realtime.llm import BosonRealtimeLLMService

from factory.agent_spec.models import AgentSpec, ClientTool
from factory.ports import (
    DEFAULT_CLOCK,
    AudioDelta,
    Clock,
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

OPEN_TIMEOUT_S = 10.0
_QUOTA_CLOSE = 4429  # F13
_CONCURRENCY_CLOSE = 1013  # F21
_END = object()


class _TappedService(BosonRealtimeLLMService):
    """Reports raw traffic to three callbacks; changes no pipecat behaviour except two."""

    def __init__(
        self,
        *,
        on_inbound: Callable[[dict[str, Any]], Any],
        on_outbound: Callable[[dict[str, Any]], None],
        on_disconnect: Callable[[int | None], None],
        wire_tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if wire_tools:
            # Raw wire dicts (F10). The `tools=` constructor argument would run pipecat's
            # handler registration, which only accepts FunctionSchema objects.
            self._boson_runtime_tools = wire_tools
        self._on_inbound = on_inbound
        self._on_outbound = on_outbound
        self._on_disconnect = on_disconnect

    async def _dispatch_boson_server_event(self, event: dict[str, Any]) -> bool:
        self._on_inbound(event)
        return await super()._dispatch_boson_server_event(event)

    async def _ws_send(self, realtime_message: Any) -> None:
        if isinstance(realtime_message, dict):
            self._on_outbound(realtime_message)
        await super()._ws_send(realtime_message)

    async def _mark_websocket_disconnected(self) -> None:
        websocket = self._websocket
        if websocket is not None:
            self._on_disconnect(getattr(websocket, "close_code", None))
        await super()._mark_websocket_disconnected()

    async def _handle_evt_function_call_arguments_done(self, evt: Any) -> None:
        # The gate answers client tools itself (`send_tool_output`); pipecat's own dispatch
        # must stay silent, so nothing is registered and nothing is sent from here.
        return None


class BosonRealtimeSession:
    def __init__(self, url: str, api_key: str | None, clock: Clock = DEFAULT_CLOCK) -> None:
        self._url = url
        self._api_key = api_key
        self._clock = clock
        self._service: _TappedService | None = None
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._ready: asyncio.Future[None] | None = None
        self._closing = False
        self._ended = False
        self._append_t = 0.0
        self._server_calls: set[str] = set()  # F10: call_ids the server runs
        self._emitted_calls: set[str] = set()
        self._call_names: dict[str, str] = {}

    # --- port ---------------------------------------------------------------------------

    async def open(self, spec: AgentSpec) -> None:
        loop = asyncio.get_running_loop()
        self._ready = loop.create_future()
        service = _TappedService(
            on_inbound=self._on_inbound,
            on_outbound=self._on_outbound,
            on_disconnect=self._on_disconnect,
            wire_tools=[_tool_payload(tool) for tool in spec.tools],
            url=self._url,
            api_key=self._api_key,
            voice=spec.voice,
            instructions=spec.instructions,
            output_modalities=["audio"],  # F6
            temperature=spec.temperature,
            max_output_tokens=spec.max_output_tokens if spec.max_output_tokens else "inf",
            turn_detection=(
                None
                if spec.turn_detection is None  # F24: null = manual commit
                else {"type": "server_vad", **spec.turn_detection.model_dump()}
            ),
        )
        self._service = service
        await service.setup(
            FrameProcessorSetup(
                clock=SystemClock(),
                task_manager=TaskManager(),
                pipeline_worker=None,  # type: ignore[arg-type]
            )
        )
        await service.process_frame(StartFrame(), FrameDirection.DOWNSTREAM)  # F1: session.update
        if service._websocket is None and not self._ready.done():
            self._ready.set_exception(SessionRefused("could not connect to the Realtime server"))
        try:
            await asyncio.wait_for(self._ready, OPEN_TIMEOUT_S)
        except TimeoutError:
            await self.close()
            raise SessionRefused(f"no session.created within {OPEN_TIMEOUT_S:.0f} s") from None
        except SessionRefused:
            await self.close()
            raise

    async def send_audio(self, pcm: bytes) -> float:
        service = self._require_service()
        await service.send_client_event(
            {"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()}  # F4
        )
        return self._append_t

    async def send_tool_output(self, call_id: str, output: str) -> None:
        service = self._require_service()
        await service.send_client_event(  # F3: exactly one item
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": output},
            }
        )
        # The server does not continue on its own after a tool output: a live gate run hung
        # here on 2026-10-24. pipecat-boson's own context path follows the output with
        # response.create (vendor-ref test_completed_function_call_output_creates_follow_up_
        # response). We send the same tagged event as its `_create_response`, without the
        # pipecat context setup this session does not use; the tag keeps the reply from being
        # dropped as a stale response.
        event_id = str(uuid.uuid4())
        service._boson_pending_response_client_event_ids.add(event_id)
        await service.send_client_event(
            {
                "event_id": event_id,
                "type": "response.create",
                "response": {"metadata": {"client_event_id": event_id}},
            }
        )

    async def events(self) -> AsyncIterator[SessionEvent]:
        while True:
            item = await self._queue.get()
            if item is _END:
                return
            yield item

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        service = self._service
        if service is not None:
            try:
                await service.process_frame(EndFrame(), FrameDirection.DOWNSTREAM)
                await service.cleanup()
            except Exception:  # noqa: BLE001 - best-effort teardown; the stream must still end
                pass
        self._queue.put_nowait(_END)

    # --- taps (called from inside pipecat's receive task) -------------------------------

    def _on_outbound(self, message: dict[str, Any]) -> None:
        if message.get("type") == "input_audio_buffer.append":
            self._append_t = self._clock()

    def _on_disconnect(self, close_code: int | None) -> None:
        if self._closing:
            return
        ready = self._ready
        if ready is not None and not ready.done():
            ready.set_exception(
                SessionRefused(f"closed before session.created (code {close_code})")
            )
            return
        if close_code == _QUOTA_CLOSE:  # F13
            self._end("quota refused", close_code, None)
        elif close_code == _CONCURRENCY_CLOSE:  # F21
            self._end("concurrency limit", close_code, None)
        else:
            self._end("closed", close_code, None)

    def _on_inbound(self, event: dict[str, Any]) -> None:
        t = self._clock()
        kind = event.get("type")
        ready = self._ready
        if ready is not None and not ready.done():
            if kind == "session.created":  # F1, F14: only the first update is acked this way
                ready.set_result(None)
                return
            if kind == "error":  # F7, F14: refused configuration
                ready.set_exception(SessionRefused(_error_text(event)))
                return
        if self._ended:
            return
        for mapped in self._map(event, kind, t):
            self._queue.put_nowait(mapped)
        if kind == "error" and _error_type(event) == "insufficient_quota":  # F13
            self._end("quota refused", None, _error_text(event))
        elif kind == "session.idle_timeout":  # F8
            self._end("idle timeout", None, None)

    # --- mapping ------------------------------------------------------------------------

    def _map(self, event: dict[str, Any], kind: Any, t: float) -> list[SessionEvent]:
        if kind == "response.output_audio.delta":  # F17
            try:
                nbytes = len(base64.b64decode(event.get("delta") or "", validate=True))
            except (binascii.Error, ValueError, TypeError):
                return [OtherEvent(str(kind), t)]
            return [AudioDelta(str(event.get("response_id", "")), nbytes, t)]
        if kind == "response.output_audio_transcript.delta":  # F18
            return [
                TranscriptDelta(str(event.get("response_id", "")), str(event.get("delta", "")), t)
            ]
        if kind == "response.created":  # F17
            response = event.get("response")
            response = response if isinstance(response, dict) else {}
            return [ResponseCreated(str(response.get("id", "")), t)]
        if kind == "response.done":  # F2, F17
            response = event.get("response")
            response = response if isinstance(response, dict) else {}
            return [
                ResponseDone(
                    str(response.get("id", "")),
                    str(response.get("status", "")),
                    _usage(response.get("usage")),
                    t,
                )
            ]
        if kind == "input_audio_buffer.speech_started":  # F15
            return [SpeechStarted(t)]
        if kind == "input_audio_buffer.speech_stopped":  # F15
            return [SpeechStopped(t)]
        if kind in (
            "response.output_item.added",
            "response.output_item.done",
            "conversation.item.added",
        ):
            return self._on_item(event.get("item"), t)
        if kind == "response.function_call_arguments.done":
            return self._on_arguments_done(event, t)
        if kind == "session.created":
            return []
        return [OtherEvent(str(kind), t)]

    def _on_item(self, item: Any, t: float) -> list[SessionEvent]:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            return []
        call_id = item.get("call_id")
        if not isinstance(call_id, str):
            return []
        if isinstance(item.get("name"), str):
            self._call_names[call_id] = item["name"]
        if item.get("executor") == "server":  # F10: the server runs it; we send nothing
            self._server_calls.add(call_id)
            if call_id not in self._emitted_calls:
                self._emitted_calls.add(call_id)
                call = ToolCall(
                    call_id,
                    self._call_names.get(call_id, ""),
                    _arguments(item.get("arguments")),
                    "server",
                    t,
                )
                return [call]
        return []

    def _on_arguments_done(self, event: dict[str, Any], t: float) -> list[SessionEvent]:
        call_id = event.get("call_id")
        if not isinstance(call_id, str) or call_id in self._server_calls:
            return []
        if call_id in self._emitted_calls:
            return []
        self._emitted_calls.add(call_id)
        name = event.get("name") if isinstance(event.get("name"), str) else None
        return [
            ToolCall(
                call_id,
                name or self._call_names.get(call_id, ""),
                _arguments(event.get("arguments")),
                "client",
                t,
            )
        ]

    def _end(self, cause: Any, close_code: int | None, error_text: str | None) -> None:
        if self._ended:
            return
        self._ended = True
        self._queue.put_nowait(SessionEnded(cause, close_code, error_text, self._clock()))
        self._queue.put_nowait(_END)

    def _require_service(self) -> _TappedService:
        if self._service is None:
            raise RuntimeError("open() was not called")
        return self._service


def _tool_payload(tool: Any) -> dict[str, Any]:
    if isinstance(tool, ClientTool):
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
    return {"type": "web_search"}  # F10


def _error_body(event: dict[str, Any]) -> dict[str, Any]:
    # The full `error` shape is UNVERIFIED (F13 names only type "insufficient_quota"):
    # accept the fields nested under "error" or flat on the event.
    nested = event.get("error")
    return nested if isinstance(nested, dict) else event


def _error_type(event: dict[str, Any]) -> str | None:
    value = _error_body(event).get("type")
    return value if isinstance(value, str) else None


def _error_text(event: dict[str, Any]) -> str:
    body = _error_body(event)
    for key in ("message", "code", "type"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    nested = event.get("error")
    return nested if isinstance(nested, str) and nested else "server error"


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _usage(raw: Any) -> Usage | None:
    """F2: `usage` is populated on the wire although the docs say null; strict about counts."""
    if not isinstance(raw, dict):
        return None
    details = raw.get("input_token_details")
    cached = _count(details.get("cached_tokens")) if isinstance(details, dict) else None
    input_tokens = _count(raw.get("input_tokens"))
    output_tokens = _count(raw.get("output_tokens"))
    if input_tokens is None or output_tokens is None or cached is None:
        return None
    return Usage(input_tokens, cached, output_tokens)
