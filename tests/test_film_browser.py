"""The Playwright page adapter against the real demo page served on loopback over a
FakeSessionFactory (no Boson credits, no real microphone).

The pure event conversion is an offline test. Everything that opens Chromium is `live`: in this
suite that marker also means "needs Chromium" (spike lane S). The three live-credit tests of the
plan (a real reply to the fake microphone, a candidate take's audio track, three unattended
takes) are in the main session's step 24 run and are not here.
"""

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from factory.film.browser_playwright import PlaywrightPage, convert_event
from factory.film.page_port import (
    AssistantChunk,
    BannerShown,
    CallerPlayed,
    PageEvent,
    PlaybackStopped,
    Ready,
    RequestBlocked,
    SessionEndedShown,
    SpeechStartedSignal,
    StatusShown,
    TranscriptShown,
    TtfaShown,
)
from factory.live.session import LiveAudioDelta
from factory.ports import ResponseCreated, SpeechStopped
from tests.doubles import Delay, FakeSessionFactory
from tests.test_film_spike import _factory_app, _serve, _tone

ST = "specialist-training"
RATE = 24000


# --- event conversion (offline) --------------------------------------------------------------


def test_convert_event_seconds_and_kinds() -> None:
    assert convert_event({"kind": "ready", "t": 1500.0, "released": True}) == Ready(1.5, True)
    assert convert_event({"kind": "ready", "t": 10.0}) == Ready(0.01, None)
    assert convert_event({"kind": "speech_started", "t": 2000}) == SpeechStartedSignal(2.0)
    assert convert_event({"kind": "clear", "t": 2000}) == SpeechStartedSignal(2.0)
    assert convert_event({"kind": "ttfa", "t": 3000, "ms": 117.4, "label": "x"}) == TtfaShown(
        3.0, 117.4, "x"
    )  # `ms` is the product's own milliseconds, not a page time
    assert convert_event({"kind": "transcript", "t": 4000, "text": "hi"}) == TranscriptShown(
        4.0, "hi"
    )
    assert convert_event({"kind": "ended", "t": 5000, "reason": "r", "message": "m"}) == (
        SessionEndedShown(5.0, "r", "m")
    )
    chunk = {"kind": "chunk", "t": 6100, "t_received": 6000.0, "start": 6050.0, "end": 7050.0}
    assert convert_event(chunk) == AssistantChunk(6.0, 6.05, 7.05)
    assert convert_event({"kind": "status", "t": 100, "text": "Live."}) == StatusShown(0.1, "Live.")
    assert convert_event({"kind": "blocked", "t": 100, "label": "gate run"}) == RequestBlocked(
        0.1, "gate run"
    )


def test_convert_event_stop_uses_the_moment_the_source_stops() -> None:
    raw = {"kind": "stop", "t": 9000.0, "start": 8000.0, "end": 9500.0, "stop_at": 9020.0}
    assert convert_event(raw) == PlaybackStopped(9.02)


def test_convert_event_caller_time_is_the_scheduled_start() -> None:
    raw = {"kind": "caller", "t": 3000.0, "id": "T2", "duration": 1.25, "emitted": 2990.0}
    assert convert_event(raw) == CallerPlayed(3.0, "T2", 1.25)


def test_convert_event_drops_bookkeeping_and_unknown_lines() -> None:
    for kind in ("ctx", "gum", "sync", "take", "caller_cancelled", "mystery"):
        assert convert_event({"kind": kind, "t": 1.0}) is None
    assert convert_event({"kind": "banner", "t": 1.0, "hidden": True}) is None
    assert convert_event({"kind": "banner", "t": 1.0, "hidden": False}) == BannerShown(0.001)
    assert convert_event({"kind": "caller", "t": 1.0, "id": "x1", "duration": 1}) is None


# --- rig: demo page on loopback, one PlaywrightPage ------------------------------------------


class Spy:
    """ASGI wrapper that records every HTTP request and WebSocket the server sees."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.seen: list[tuple[str, str]] = []

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            self.seen.append((scope["method"], scope["path"]))
        elif scope["type"] == "websocket":
            self.seen.append(("WS", scope["path"]))
        await self.app(scope, receive, send)


class Rig:
    def __init__(self, page: PlaywrightPage) -> None:
        self.page = page
        self.events: list[PageEvent] = []
        self._drain = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        async for event in self.page.events():
            self.events.append(event)

    async def wait[T](
        self, find: Callable[[list[PageEvent]], T | None], timeout_s: float = 15
    ) -> T:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            found = find(self.events)
            if found is not None:
                return found
            await asyncio.sleep(0.02)
        raise AssertionError(f"timed out; saw {[type(e).__name__ for e in self.events]}")

    async def first(self, cls: type, timeout_s: float = 15) -> Any:
        return await self.wait(
            lambda ev: next((e for e in ev if isinstance(e, cls)), None), timeout_s
        )

    async def close(self) -> None:
        await self.page.close()
        await asyncio.wait_for(self._drain, 5)  # events() ends after close()


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _serve_spy(tmp_path: Path, factory: FakeSessionFactory) -> tuple[Any, Spy]:
    from factory.web.app import create_web_app

    spy = Spy(create_web_app(_factory_app(tmp_path, factory)))
    return _serve(spy), spy


def _reply_script() -> list[Any]:
    agent = _tone(880, 1.0)
    return [
        SpeechStopped(0.0),
        ResponseCreated("r1", 0.0),
        Delay(0.6),
        LiveAudioDelta("r1", len(agent), 0.0, pcm=agent),
        Delay(60.0),
    ]


# --- fake-server Chromium tests --------------------------------------------------------------


@pytest.mark.live
def test_ttfa_label_in_viewport(tmp_path: Path) -> None:
    """The measured-from label and the TTFA list lie inside the 1920x1080 frame during the take."""
    factory = FakeSessionFactory(_reply_script(), restamp=True)
    serving, _ = _serve_spy(tmp_path, factory)

    async def scenario(base: str) -> dict[str, tuple[float, float, float, float]]:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            await rig.page.load_caller("T1", _tone(440, 0.5))
            await rig.page.begin_take()
            await rig.page.click_start()
            ready = await rig.first(Ready)
            await rig.page.play_caller("T1", ready.t + 0.3)
            await rig.first(TtfaShown)
            return await rig.page.boxes(["#ttfaLabel", "#ttfaList"])
        finally:
            await rig.close()

    with serving as base:
        boxes = _run(scenario(base))
    assert set(boxes) == {"#ttfaLabel", "#ttfaList"}
    for x, y, w, h in boxes.values():
        assert x >= 0 and y >= 0 and w > 0 and h > 0
        assert x + w <= 1920 and y + h <= 1080, (x, y, w, h)


@pytest.mark.live
def test_route_guard_blocks_gate_click_in_chromium(tmp_path: Path) -> None:
    """A click on "Run full gate" never reaches the server: the page adapter aborts it and
    reports `RequestBlocked("gate run")`."""
    serving, spy = _serve_spy(tmp_path, FakeSessionFactory([]))

    async def scenario(base: str) -> list[PageEvent]:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            await rig.page.click("#runGate")
            await rig.wait(lambda ev: next((e for e in ev if isinstance(e, RequestBlocked)), None))
            return list(rig.events)
        finally:
            await rig.close()

    with serving as base:
        events = _run(scenario(base))
    blocked = [e for e in events if isinstance(e, RequestBlocked)]
    assert [b.label for b in blocked] == ["gate run"]
    assert blocked[0].t > 0
    assert not [s for s in spy.seen if s[0] == "POST"], spy.seen


@pytest.mark.live
def test_no_ws_during_page_beats(tmp_path: Path) -> None:
    """Opening the page, choosing an agent and showing parts of it opens no live session."""
    serving, spy = _serve_spy(tmp_path, FakeSessionFactory([]))

    async def scenario(base: str) -> None:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            await rig.page.sync_mark()
            await rig.page.show("#startBtn")
            await asyncio.sleep(0.5)
        finally:
            await rig.close()

    with serving as base:
        _run(scenario(base))
    assert not [s for s in spy.seen if s[0] == "WS"], spy.seen
    assert ("GET", "/api/templates") in spy.seen


@pytest.mark.live
def test_boxes_skip_missing_elements_and_avatar_is_unticked(tmp_path: Path) -> None:
    serving, _ = _serve_spy(tmp_path, FakeSessionFactory([]))

    async def scenario(base: str) -> tuple[Any, bool]:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            boxes = await rig.page.boxes(["#startBtn", "#no-such-element"])
            return boxes, await rig.page.avatar_ticked()
        finally:
            await rig.close()

    with serving as base:
        boxes, ticked = _run(scenario(base))
    assert list(boxes) == ["#startBtn"]
    assert ticked is False


@pytest.mark.live
def test_select_agent_unknown_id_is_an_error(tmp_path: Path) -> None:
    serving, _ = _serve_spy(tmp_path, FakeSessionFactory([]))

    async def scenario(base: str) -> None:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent("no-such-agent")
        finally:
            await rig.close()

    with serving as base, pytest.raises(LookupError):
        _run(scenario(base))


@pytest.mark.live
def test_video_is_finalized_at_the_given_path_and_events_end(tmp_path: Path) -> None:
    serving, _ = _serve_spy(tmp_path, FakeSessionFactory([]))
    video = tmp_path / "runs" / "r" / "page-b4.video.webm"

    async def scenario(base: str) -> int:
        page = PlaywrightPage()
        rig = Rig(page)
        await page.open(base, video)
        await page.select_agent(ST)
        await asyncio.sleep(1.0)
        await rig.close()  # also proves `events()` ends after close()
        await page.close()  # idempotent
        return len(rig.events)

    with serving as base:
        _run(scenario(base))
    data = video.read_bytes()
    assert data[:4] == b"\x1a\x45\xdf\xa3", "not a webm/matroska file"
    assert len(data) > 1000
    assert [p.name for p in video.parent.iterdir()] == [video.name]  # no stray recordings


@pytest.mark.live
def test_take_audio_track_holds_the_page_output(tmp_path: Path) -> None:
    """begin_take .. end_take writes a decodable webm; the caller and the agent reply are both
    loud in it, and the reply's chunk and the caller's CallerPlayed carry page-clock seconds."""
    import array
    import math
    import subprocess

    factory = FakeSessionFactory(_reply_script(), restamp=True)
    serving, _ = _serve_spy(tmp_path, factory)
    out = tmp_path / "take-1.webm"

    async def scenario(base: str) -> tuple[float, list[PageEvent]]:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            await rig.page.load_caller("T1", _tone(440, 0.5))
            t0 = await rig.page.begin_take()
            await asyncio.sleep(0.4)
            await rig.page.click_start()
            ready = await rig.first(Ready)
            await rig.page.play_caller("T1", ready.t + 0.3)
            await rig.first(AssistantChunk)
            await asyncio.sleep(1.4)
            await rig.page.click_stop()
            await rig.page.end_take(out)
            return t0, list(rig.events)
        finally:
            await rig.close()

    with serving as base:
        t0, events = _run(scenario(base))
    played = next(e for e in events if isinstance(e, CallerPlayed))
    chunk = next(e for e in events if isinstance(e, AssistantChunk))
    assert played.line_id == "T1" and played.duration_s == pytest.approx(0.5, abs=0.01)
    assert chunk.end - chunk.start == pytest.approx(1.0, abs=0.02)
    assert 0 < t0 < played.t < chunk.start

    pcm = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(out)]
        + ["-f", "s16le", "-ac", "1", "-ar", str(RATE), "pipe:1"],
        capture_output=True,
        check=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])

    def rms_db(start_s: float, end_s: float) -> float:
        part = samples[int(start_s * RATE) : int(end_s * RATE)]
        mean = sum(s * s for s in part) / max(1, len(part))
        return 10 * math.log10(mean / 32768**2) if mean > 0 else -200.0

    assert rms_db(played.t - t0 + 0.1, played.t - t0 + 0.4) > -30  # the caller
    assert rms_db(chunk.start - t0 + 0.2, chunk.end - t0 - 0.2) > -30  # the agent


@pytest.mark.live
def test_t2_plays_over_the_reply_and_is_dropped_over_silence(tmp_path: Path) -> None:
    """AC-20 inside the page: T2 is spoken when an assistant source is audible at its due
    time, and is not spoken (no CallerPlayed) when none is."""
    # session A: a 1 s reply arrives ~0.6 s after T1; session B (a second page): no reply at all
    scripts = [_reply_script(), [Delay(60.0)]]
    factory = FakeSessionFactory(scripts=scripts, restamp=True)
    serving, _ = _serve_spy(tmp_path, factory)

    async def over_reply(base: str) -> tuple[AssistantChunk, CallerPlayed, float]:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            await rig.page.load_caller("T1", _tone(440, 0.5))
            await rig.page.load_caller("T2", _tone(660, 0.4))
            await rig.page.begin_take()
            await rig.page.click_start()
            ready = await rig.first(Ready)
            await rig.page.play_caller("T1", ready.t + 0.3)
            chunk = await rig.first(AssistantChunk)
            due = chunk.t_received + 0.4
            await rig.page.play_caller("T2", due)
            t2 = await rig.wait(
                lambda ev: next(
                    (e for e in ev if isinstance(e, CallerPlayed) and e.line_id == "T2"), None
                )
            )
            return chunk, t2, due
        finally:
            await rig.close()

    async def over_silence(base: str) -> list[PageEvent]:
        rig = Rig(PlaywrightPage())
        try:
            await rig.page.open(base, None)
            await rig.page.select_agent(ST)
            await rig.page.load_caller("T2", _tone(660, 0.4))
            await rig.page.begin_take()
            await rig.page.click_start()
            ready = await rig.first(Ready)
            await rig.page.play_caller("T2", ready.t + 0.5)
            await asyncio.sleep(1.5)
            return list(rig.events)
        finally:
            await rig.close()

    with serving as base:
        chunk, t2, due = _run(over_reply(base))
        events = _run(over_silence(base))
    assert abs(t2.t - due) <= 0.05, (t2.t, due)
    assert t2.duration_s == pytest.approx(0.4, abs=0.01)
    assert chunk.start <= t2.t < chunk.end
    assert not [e for e in events if isinstance(e, CallerPlayed)], events
    assert not [e for e in events if isinstance(e, SessionEndedShown)], events
