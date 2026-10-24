"""Plan step 26: `run_live`, the live session service (AC-26, AC-35, AC-43, AC-44).

Offline: a controllable fake session and a recording sink; one wire test runs the real session
adapter against the fake Realtime server.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

from factory.agent_spec.models import AgentSpec
from factory.agent_spec.validation import validate_agent_spec
from factory.composition import LiveBosonSession
from factory.live.session import LIVE_TTFA_LABEL, LiveAudioDelta, LiveEnd, run_live
from factory.ports import (
    AudioDelta,
    ResponseCreated,
    ResponseDone,
    SessionEnded,
    SessionEvent,
    SessionRefused,
    SpeechStarted,
    SpeechStopped,
    ToolCall,
    TranscriptDelta,
)
from tests.doubles import make_spec
from tests.fake_realtime_server import (
    audio_delta_event,
    close,
    fake_realtime_server,
    idle_timeout_event,
    response_done_event,
    send,
    speech_started_event,
    speech_stopped_event,
    wait_for,
)

WAIT_S = 10.0
_END = object()


def _spec(**budget: Any) -> AgentSpec:
    raw = make_spec()
    raw["budget"].update(budget)
    raw["tools"] = [
        {
            "kind": "client",
            "name": "lookup",
            "description": "d",
            "parameters": {"type": "object"},
            "mock": {"default_output": "MOCK-OUT", "by_argument": []},
        }
    ]
    spec = validate_agent_spec(raw)
    assert isinstance(spec, AgentSpec)
    return spec


class LiveFake:
    """A session whose events the test pushes while `run_live` is running."""

    def __init__(self, refuse: str | None = None, fail_send: bool = False) -> None:
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.refuse = refuse
        self.fail_send = fail_send
        self.open_calls = 0
        self.closed = False
        self.audio: list[bytes] = []
        self.tool_outputs: list[tuple[str, str]] = []

    async def open(self, spec: AgentSpec) -> None:
        self.open_calls += 1
        if self.refuse is not None:
            raise SessionRefused(self.refuse)

    async def send_audio(self, pcm: bytes) -> float:
        if self.fail_send:
            raise ConnectionError("socket gone")
        self.audio.append(pcm)
        return time.monotonic()

    async def send_tool_output(self, call_id: str, output: str) -> None:
        self.tool_outputs.append((call_id, output))

    async def events(self) -> AsyncIterator[SessionEvent]:
        while True:
            item = await self.queue.get()
            if item is _END:
                return
            yield item

    async def close(self) -> None:
        self.closed = True
        self.queue.put_nowait(_END)

    def push(self, *events: SessionEvent) -> None:
        for event in events:
            self.queue.put_nowait(event)


class Sink:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def opened(self) -> None:
        self.calls.append(("opened", None))

    async def audio(self, pcm: bytes) -> None:
        self.calls.append(("audio", pcm))

    async def stop_playback(self, response_id: str | None) -> None:
        self.calls.append(("stop_playback", response_id))

    async def ttfa(self, ms: float, label: str) -> None:
        self.calls.append(("ttfa", (ms, label)))

    async def transcript(self, text: str) -> None:
        self.calls.append(("transcript", text))

    async def ended(self, reason: str, message: str) -> None:
        self.calls.append(("ended", (reason, message)))

    def of(self, kind: str) -> list[Any]:
        return [v for k, v in self.calls if k == kind]


async def _forever() -> AsyncIterator[bytes]:
    await asyncio.Event().wait()
    yield b""  # pragma: no cover


async def _frames(*frames: bytes, then_wait: bool = True) -> AsyncIterator[bytes]:
    for frame in frames:
        yield frame
    if then_wait:
        await asyncio.Event().wait()


def _drive(spec: AgentSpec, fake: LiveFake, sink: Sink, mic: Any, feed: Any = None) -> LiveEnd:
    async def main() -> LiveEnd:
        task = asyncio.create_task(run_live(spec, fake, mic, sink))
        if feed is not None:
            await feed()
        return await asyncio.wait_for(task, WAIT_S)

    return asyncio.run(main())


def test_ac26_ttfa_three_turns_from_speech_stopped() -> None:
    fake, sink = LiveFake(), Sink()
    for i, rid in enumerate(("r1", "r2", "r3")):
        base = 100.0 + i * 10
        fake.push(
            SpeechStopped(base),
            ResponseCreated(rid, base + 0.1),
            LiveAudioDelta(rid, 4, base + 0.3, pcm=b"\x01\x00\x02\x00"),
            LiveAudioDelta(rid, 4, base + 0.4, pcm=b"\x01\x00\x02\x00"),
            ResponseDone(rid, "completed", None, base + 0.5),
        )
    fake.push(SessionEnded("closed", None, None, 200.0))
    end = _drive(_spec(), fake, sink, _forever())
    values = sink.of("ttfa")
    assert len(values) == 3  # one per turn, not per delta
    assert all(abs(ms - 300.0) < 1.0 and label == LIVE_TTFA_LABEL for ms, label in values)
    assert "speech_stopped" in LIVE_TTFA_LABEL
    assert end.reason == "closed" and fake.closed
    assert sink.calls[0] == ("opened", None) and sink.calls[-1][0] == "ended"


def test_audio_forwarding_both_ways_and_transcript() -> None:
    fake, sink = LiveFake(), Sink()
    pcm = b"\x05\x00" * 4
    fake.push(
        ResponseCreated("r1", 1.0),
        LiveAudioDelta("r1", len(pcm), 1.1, pcm=pcm),
        AudioDelta("r2", 4, 1.2),  # a plain delta carries no PCM: nothing to forward
        TranscriptDelta("r1", "Hello ", 1.2),
        TranscriptDelta("r1", "there.", 1.2),
        ResponseDone("r1", "completed", None, 1.3),
    )

    async def feed() -> None:
        while len(fake.audio) < 2 or not sink.of("transcript"):
            await asyncio.sleep(0.01)
        fake.push(SessionEnded("closed", None, None, 2.0))

    _drive(_spec(), fake, sink, _frames(b"\x01\x00", b"\x02\x00"), feed)
    assert fake.audio == [b"\x01\x00", b"\x02\x00"]
    assert sink.of("audio") == [pcm]
    assert sink.of("transcript") == ["Hello there."]


def test_barge_in_stops_playback_and_drops_late_deltas() -> None:
    fake, sink = LiveFake(), Sink()
    fake.push(
        ResponseCreated("r1", 1.0),
        LiveAudioDelta("r1", 2, 1.1, pcm=b"AA"),
        SpeechStarted(1.2),
        LiveAudioDelta("r1", 2, 1.25, pcm=b"LATE"),  # the cancelled response's stragglers
        TranscriptDelta("r1", "cut off", 1.25),
        ResponseDone("r1", "cancelled", None, 1.3),
        SpeechStopped(2.0),
        ResponseCreated("r2", 2.1),
        LiveAudioDelta("r2", 2, 2.4, pcm=b"BB"),
        SessionEnded("closed", None, None, 3.0),
    )
    _drive(_spec(), fake, sink, _forever())
    assert sink.of("stop_playback") == ["r1"]
    assert sink.of("audio") == [b"AA", b"BB"]
    assert sink.of("transcript") == []
    (ms, _) = sink.of("ttfa")[0]
    assert abs(ms - 400.0) < 1.0


def test_client_tool_call_is_answered_with_the_spec_mock() -> None:
    fake, sink = LiveFake(), Sink()
    fake.push(
        ToolCall("c1", "lookup", {"q": 1}, "client", 1.0),
        ToolCall("c2", "web_search", {}, "server", 1.0),
        SessionEnded("closed", None, None, 2.0),
    )
    _drive(_spec(), fake, sink, _forever())
    assert fake.tool_outputs == [("c1", "MOCK-OUT")]


def test_ac35_limit_reached_closes_the_session() -> None:
    fake, sink = LiveFake(), Sink()
    started = time.monotonic()
    end = _drive(_spec(max_live_session_s=0.4), fake, sink, _forever())
    elapsed = time.monotonic() - started
    assert end.reason == "limit reached" and "0.4" in end.message
    assert 0.35 <= elapsed < 3.0
    assert fake.closed and sink.of("ended")[0][0] == "limit reached"


def test_ac43_idle_timeout_is_inactivity() -> None:
    fake, sink = LiveFake(), Sink()
    fake.push(SessionEnded("idle timeout", None, None, 1.0))
    end = _drive(_spec(), fake, sink, _forever())
    assert end.reason == "inactivity" and "inactivity" in end.message
    assert fake.closed


@pytest.mark.parametrize("how", ["ended", "refused"])
def test_ac44_quota_refused_never_reopens(how: str) -> None:
    fake, sink = (
        LiveFake(refuse="closed before session.created (code 4429)" if how == "refused" else None),
        Sink(),
    )
    if how == "ended":
        fake.push(SessionEnded("quota refused", 4429, None, 1.0))
    end = _drive(_spec(), fake, sink, _forever())
    assert end.reason == "quota refused"
    assert fake.open_calls == 1  # no reconnect
    assert sink.of("ended") == [("quota refused", end.message)]
    assert fake.closed


def test_other_refusal_is_an_error_with_the_server_text() -> None:
    fake, sink = LiveFake(refuse="voice not found"), Sink()
    end = _drive(_spec(), fake, sink, _forever())
    assert end.reason == "error" and "voice not found" in end.message
    assert sink.of("opened") == []


def test_mic_ending_closes_the_session() -> None:
    fake, sink = LiveFake(), Sink()
    end = _drive(_spec(), fake, sink, _frames(b"\x01\x00", then_wait=False))
    assert end.reason == "closed" and fake.closed
    assert fake.audio == [b"\x01\x00"]


def test_failed_send_ends_with_error_and_nothing_hangs() -> None:
    fake, sink = LiveFake(fail_send=True), Sink()
    end = _drive(_spec(), fake, sink, _frames(b"\x01\x00"))
    assert end.reason == "error" and "ConnectionError" in end.message
    assert "socket gone" not in end.message  # exception text is not passed on
    assert fake.closed


def test_cancelling_run_live_still_closes_the_session() -> None:
    fake, sink = LiveFake(), Sink()

    async def main() -> None:
        task = asyncio.create_task(run_live(_spec(), fake, _forever(), sink))
        while not sink.of("opened"):
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    assert fake.closed


# --- the real session adapter against the fake Realtime server -----------------------------


def test_wire_audio_pcm_idle_timeout_and_quota() -> None:
    quota = {"type": "error", "error": {"type": "insufficient_quota", "message": "refused"}}

    async def one(script: list[Any], **budget: Any) -> tuple[LiveEnd, Sink]:
        sink = Sink()
        async with fake_realtime_server(script) as (url, _):
            session = LiveBosonSession(url=url, api_key="k")
            end = await asyncio.wait_for(
                run_live(_spec(**budget), session, _forever(), sink), WAIT_S
            )
        return end, sink

    async def main() -> None:
        end, sink = await one(
            [
                wait_for("session.update"),
                send(speech_stopped_event()),
                send(audio_delta_event("r1", 4800)),
                send(response_done_event("r1")),
                send(idle_timeout_event()),
            ]
        )
        assert end.reason == "inactivity"
        assert [len(p) for p in sink.of("audio")] == [4800]
        assert len(sink.of("ttfa")) == 1

        end, _ = await one([wait_for("session.update"), send(quota), close(4429)])
        assert end.reason == "quota refused"

        end, _ = await one([close(4429)])  # refused before session.created
        assert end.reason == "quota refused"

        end, sink = await one(
            [
                wait_for("session.update"),
                send(audio_delta_event("r1", 960)),
                send(speech_started_event()),
                wait_for("never.sent"),  # the server stays silent: only the limit can end it
            ],
            max_live_session_s=0.5,
        )
        assert end.reason == "limit reached"
        assert sink.of("stop_playback") == ["r1"] and len(sink.of("audio")) == 1

    asyncio.run(main())
