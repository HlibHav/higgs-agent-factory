"""`PagePort` over Python Playwright (Chromium, headless) and `page/tap.js`.

Adapter layer: the only module that imports `playwright`, and it does so inside `open`, so the
rest of the recorder (and the tests that never open a browser) load without it. `tap.js` is an
init script: it gives the unchanged product page a fake microphone in the page's own 24 kHz
context, taps what the page plays, and reports what happens through the `__filmEvent` binding as
JSON with times in `performance.now()` milliseconds. This module converts them to the seconds of
`page_port` and answers the port's calls with `page.evaluate` into `window.__film`.
"""

import asyncio
import base64
import json
import shutil
import tempfile
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from factory.film.guard import blocked_label
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

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright, Route

TAP_JS = Path(__file__).parent / "page" / "tap.js"
VIEWPORT = {"width": 1920, "height": 1080}
CHROMIUM_ARGS = ["--autoplay-policy=no-user-gesture-required"]  # no fake-device flag (spike S-3)
BINDING = "__filmEvent"
TEMPLATE_WAIT_MS = 15_000
ACTION_WAIT_MS = 5_000
CALLER_IDS = ("T1", "T2")
_SENTINEL = object()


def _s(ms: Any) -> float:
    return float(ms) / 1000.0


def convert_event(raw: Mapping[str, Any]) -> PageEvent | None:
    """One `tap.js` event (JSON, milliseconds) as a `PageEvent` (seconds), or None when the
    event is only bookkeeping (`ctx`, `gum`, `sync`, `take`, a visible-to-hidden banner...)."""
    kind = raw.get("kind")
    t = _s(raw.get("t", 0.0))
    match kind:
        case "ready":
            released = raw.get("released")
            return Ready(t, released if isinstance(released, bool) else None)
        case "speech_started" | "clear":
            return SpeechStartedSignal(t)
        case "ttfa":
            return TtfaShown(t, float(raw.get("ms", 0.0)), str(raw.get("label", "")))
        case "transcript":
            return TranscriptShown(t, str(raw.get("text", "")))
        case "ended":
            return SessionEndedShown(t, str(raw.get("reason", "")), str(raw.get("message", "")))
        case "chunk":
            return AssistantChunk(_s(raw["t_received"]), _s(raw["start"]), _s(raw["end"]))
        case "stop":
            # the moment the source really stops sounding, in context time converted to page time
            return PlaybackStopped(_s(raw.get("stop_at", raw.get("t", 0.0))))
        case "banner":
            return None if raw.get("hidden", True) else BannerShown(t)
        case "caller":
            line_id = raw.get("id")
            if line_id not in CALLER_IDS:
                return None
            return CallerPlayed(
                t, cast(Literal["T1", "T2"], line_id), float(raw.get("duration", 0.0))
            )
        case "blocked":
            return RequestBlocked(t, str(raw.get("label", "")))
        case "status":
            return StatusShown(t, str(raw.get("text", "")))
    return None


class PlaywrightPage:
    """One Chromium page per instance; `open` starts the browser, `close` ends everything."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._video_path: Path | None = None
        self._video_dir: Path | None = None
        self._closed = False
        self._mono_at_open = 0.0
        self._open_perf = 0.0

    # -- events --

    def _on_binding(self, _source: Any, raw: str) -> None:
        try:
            event = convert_event(json.loads(raw))
        except (ValueError, KeyError, TypeError):
            return  # a malformed line from the page is not an event
        if event is not None:
            self._queue.put_nowait(event)

    async def events(self) -> AsyncIterator[PageEvent]:
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                self._queue.put_nowait(_SENTINEL)  # any later iterator ends too
                return
            yield cast(PageEvent, item)

    # -- guard --

    async def _route(self, route: "Route") -> None:
        request = route.request
        label = blocked_label(request.method, request.url)
        if label is None:
            await route.continue_()
            return
        await route.abort("blockedbyclient")
        # `tap.js` stamps the page clock and sends the event through the same binding
        try:
            assert self._page is not None
            await self._page.evaluate("(l) => window.__film && window.__film.blocked(l)", label)
        except Exception:  # noqa: BLE001 - the page is going away: stamp it from our own clock
            t = (time.monotonic() - self._mono_at_open) + self._open_perf
            self._queue.put_nowait(RequestBlocked(t, label))

    # -- lifecycle --

    async def open(self, base_url: str, video_path: Path | None) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        options: dict[str, Any] = {"viewport": VIEWPORT, "device_scale_factor": 1}
        if video_path is not None:
            video_path.parent.mkdir(parents=True, exist_ok=True)
            self._video_path = video_path
            self._video_dir = Path(tempfile.mkdtemp(prefix="film-video-"))
            options["record_video_dir"] = str(self._video_dir)
            options["record_video_size"] = VIEWPORT
        self._context = await self._browser.new_context(**options)
        await self._context.add_init_script(path=str(TAP_JS))
        await self._context.expose_binding(BINDING, self._on_binding)
        await self._context.route("**/*", self._route)
        self._page = await self._context.new_page()
        await self._page.goto(base_url.rstrip("/") + "/")
        self._open_perf = float(await self._page.evaluate("performance.now()")) / 1000.0
        self._mono_at_open = time.monotonic()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            video = self._page.video if self._page is not None else None
            if self._page is not None:
                await self._page.close()  # flushes the last binding calls and the video
            if video is not None and self._video_path is not None:
                await video.save_as(str(self._video_path))
            if self._context is not None:
                await self._context.close()
            if self._browser is not None:
                await self._browser.close()
            if self._pw is not None:
                await self._pw.stop()
        finally:
            if self._video_dir is not None:
                shutil.rmtree(self._video_dir, ignore_errors=True)
            self._queue.put_nowait(_SENTINEL)

    # -- the port --

    @property
    def page(self) -> "Page":
        if self._page is None:
            raise RuntimeError("the page is not open")
        return self._page

    async def select_agent(self, agent_id: str) -> None:
        """Click the template card whose `template_id` is `agent_id` (saved briefs are listed
        there too) and wait until Start is enabled."""
        page = self.page
        await page.wait_for_selector(".tcard", timeout=TEMPLATE_WAIT_MS)
        index = await page.evaluate(
            "async (id) => { const r = await fetch('/api/templates');"
            " const t = await r.json(); return t.findIndex((x) => x.template_id === id); }",
            agent_id,
        )
        if not isinstance(index, int) or index < 0:
            raise LookupError(f"the demo page lists no agent {agent_id!r}")
        await page.locator(".tcard").nth(index).click(timeout=ACTION_WAIT_MS)
        await page.wait_for_function(
            "!document.getElementById('startBtn').disabled", timeout=TEMPLATE_WAIT_MS
        )

    async def avatar_ticked(self) -> bool:
        return await self.page.locator("#avatarToggle").is_checked()

    async def show(self, target: str) -> None:
        loc = self.page.locator(target).first
        await loc.evaluate(
            "(e) => e.scrollIntoView({block: 'center', behavior: 'instant'})",
            timeout=ACTION_WAIT_MS,
        )

    async def boxes(self, locators: Sequence[str]) -> dict[str, tuple[float, float, float, float]]:
        out: dict[str, tuple[float, float, float, float]] = {}
        for sel in locators:
            try:
                box = await self.page.locator(sel).first.bounding_box(timeout=ACTION_WAIT_MS)
            except Exception:  # noqa: BLE001 - absent element: no box, the caller decides
                continue
            if box is not None:
                out[sel] = (box["x"], box["y"], box["width"], box["height"])
        return out

    async def sync_mark(self) -> float:
        return _s(await self.page.evaluate("__film.syncMark()"))

    async def load_caller(self, line_id: str, pcm: bytes) -> None:
        b64 = base64.b64encode(pcm).decode("ascii")
        await self.page.evaluate("([i, b]) => __film.loadCaller(i, b)", [line_id, b64])

    async def play_caller(self, line_id: str, at: float | None) -> None:
        """T2 carries `requireAssistant`: the page itself drops the line when no assistant
        source is audible at `at` (AC-20), and then no `CallerPlayed` follows."""
        at_ms = None if at is None else at * 1000.0
        opts = {"requireAssistant": line_id == "T2"}
        await self.page.evaluate(
            "([i, a, o]) => __film.playCaller(i, a, o)", [line_id, at_ms, opts]
        )

    async def begin_take(self) -> float:
        """Start the take recorders and flash the sync mark. Returns the page time at which the
        take's audio starts."""
        started = await self.page.evaluate(
            "(() => { __film.beginTake(); return __film.takeStart; })()"
        )
        return _s(started)

    async def click_start(self) -> None:
        await self.page.click("#startBtn", timeout=ACTION_WAIT_MS)

    async def click_stop(self) -> None:
        stop = self.page.locator("#stopBtn")
        if await stop.is_enabled():  # a session that already ended leaves Stop disabled
            await stop.click(timeout=ACTION_WAIT_MS)

    async def click(self, selector: str) -> None:
        await self.page.click(selector, timeout=ACTION_WAIT_MS)

    async def end_take(self, path: Path) -> None:
        b64 = await self.page.evaluate("__film.endTake()")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(b64))


async def open_playwright_page() -> PlaywrightPage:
    """The `PageFactory`: an unopened page; the caller opens it."""
    return PlaywrightPage()
