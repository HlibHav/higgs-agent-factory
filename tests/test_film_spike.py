"""Step-1 spike for the demo film: can a Playwright-driven Chromium speak into the unchanged
product page (fake microphone in the page's own 24 kHz context) and record what the page plays?

Both tests are `live`: they need Chromium, and the second one also spends Boson credits.
`tap.js` is loaded by path; this module imports nothing from `factory.film`.
"""

import array
import base64
import contextlib
import math
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from factory.composition import FactoryApp
from factory.gate.card_store import FileCardStore
from factory.gate.tts_cache import TurnAudioSource
from factory.live.session import LiveAudioDelta
from factory.ports import ResponseCreated
from factory.web.app import create_web_app
from tests.doubles import Delay, FakeJudge, FakeSessionFactory, FakeTts
from tests.test_film_product_unchanged import PINNED, _sha256

TAP = Path(__file__).resolve().parent.parent / "factory" / "film" / "page" / "tap.js"
RATE = 24000
FRAME_S = 0.04
LOUD_DB = -30.0
SILENT_DB = -80.0
CHROMIUM_ARGS = ["--autoplay-policy=no-user-gesture-required"]  # no fake-device flag (S-3)


# --- signals ------------------------------------------------------------------------------


def _tone(freq: float, seconds: float, amplitude: float = 0.3) -> bytes:
    n = int(RATE * seconds)
    samples = array.array(
        "h", (int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / RATE)) for i in range(n))
    )
    return samples.tobytes()


def _frames_db(pcm: bytes) -> list[float]:
    """RMS in dBFS of consecutive 40 ms frames of 16-bit mono PCM."""
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    size = int(RATE * FRAME_S)
    out: list[float] = []
    for start in range(0, len(samples) - size + 1, size):
        chunk = samples[start : start + size]
        mean_sq = sum(s * s for s in chunk) / size
        out.append(10 * math.log10(mean_sq / 32768**2) if mean_sq > 0 else -200.0)
    return out


def _rms_db(pcm: bytes, start_s: float, end_s: float) -> float:
    a, b = int(start_s * RATE) * 2, int(end_s * RATE) * 2
    frames = _frames_db(pcm[a:b])
    if not frames:
        return -200.0
    return 10 * math.log10(sum(10 ** (f / 10) for f in frames) / len(frames))


def _loud_regions(frames: list[float]) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    start: int | None = None
    for i, db in enumerate(frames):
        if db >= LOUD_DB and start is None:
            start = i
        elif db < LOUD_DB and start is not None:
            regions.append((start, i - 1))
            start = None
    if start is not None:
        regions.append((start, len(frames) - 1))
    return regions


def _decode_webm(b64: str) -> bytes:
    """ffmpeg -> raw 24 kHz mono s16le."""
    blob = base64.b64decode(b64)
    done = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(RATE),
            "pipe:1",
        ],
        input=blob,
        capture_output=True,
        check=True,
    )
    return done.stdout


# --- rig: web app on loopback + Chromium with tap.js ---------------------------------------


@contextlib.contextmanager
def _serve(app: Any) -> Iterator[str]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)


class _Page:
    """A Chromium page with tap.js and an event list fed by the `__filmEvent` binding."""

    def __init__(self, page: Page, events: list[dict[str, Any]], errors: list[str]) -> None:
        self.page = page
        self.events = events
        self.errors = errors

    def kinds(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in list(self.events) if e["kind"] == kind]

    def wait_event(self, kind: str, timeout_s: float = 15.0, after: int = 0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            found = self.kinds(kind)
            if len(found) > after:
                return found[after]
            self.page.wait_for_timeout(20)
        raise AssertionError(f"no {kind!r} event within {timeout_s}s; saw {self._seen()}")

    def _seen(self) -> list[str]:
        return [e["kind"] for e in list(self.events)]

    def evaluate(self, expr: str, arg: Any = None) -> Any:
        return self.page.evaluate(expr, arg)


@contextlib.contextmanager
def _chromium(base_url: str, video_dir: Path | None = None) -> Iterator[_Page]:
    import json

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=str(video_dir) if video_dir else None,
                record_video_size={"width": 1280, "height": 720} if video_dir else None,
            )
            context.add_init_script(path=str(TAP))
            context.expose_function("__filmEvent", lambda raw: events.append(json.loads(raw)))
            page = context.new_page()
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
            # A 404 for the favicon or "no gate run yet" is the product's normal behaviour.
            page.on(
                "console",
                lambda msg: (
                    errors.append(f"console.error: {msg.text}")
                    if msg.type == "error" and "Failed to load resource" not in msg.text
                    else None
                ),
            )
            page.goto(base_url + "/")
            yield _Page(page, events, errors)
        finally:
            browser.close()


def _start_live(film: _Page) -> None:
    film.page.wait_for_selector(".tcard", timeout=15000)
    film.page.locator(".tcard").first.click()
    film.page.wait_for_function("!document.getElementById('startBtn').disabled", timeout=15000)
    film.page.click("#startBtn")
    film.page.wait_for_function(
        "document.getElementById('liveStatus').textContent === 'Live. Speak now.'", timeout=15000
    )


def _load(film: _Page, caller_id: str, pcm: bytes) -> float:
    b64 = base64.b64encode(pcm).decode()
    return float(film.evaluate("([i, b]) => __film.loadCaller(i, b)", [caller_id, b64]))


def _factory_app(tmp_path: Path, live: Callable[[], Any]) -> FactoryApp:
    return FactoryApp(
        sessions=FakeSessionFactory(),
        audio=TurnAudioSource(FakeTts(), tmp_path / "tts", tmp_path / "rec"),
        judge=FakeJudge([]),
        store=FileCardStore(tmp_path / "cards"),
        live_sessions=live,
    )


def _live_env() -> dict[str, str]:
    """The process environment plus any missing key from `.env` (never printed)."""
    env = dict(os.environ)
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            name, sep, value = line.partition("=")
            name = name.strip().removeprefix("export ").strip()
            if sep and name and not env.get(name):
                env[name] = value.strip().strip("'\"")
    return env


# --- the spike ---------------------------------------------------------------------------


@pytest.mark.live
def test_spike_fake_session_mic_and_tap(tmp_path: Path) -> None:
    """S-1..S-5 and S-7 against a FakeSession: no Boson credits, no real microphone."""
    # S-1: the product files are the plan-start files.
    assert {p: _sha256(p) for p in PINNED} == PINNED

    t1, t2 = _tone(440, 1.5), _tone(660, 0.8)
    agent = _tone(880, 1.0)
    factory = FakeSessionFactory(
        [
            ResponseCreated("r1", 0.0),
            Delay(4.0),
            LiveAudioDelta("r1", len(agent), 0.0, pcm=agent),
            Delay(60.0),
        ]
    )
    app = create_web_app(_factory_app(tmp_path, factory))
    with _serve(app) as base, _chromium(base) as film:
        _start_live(film)

        # S-2: the page's context is the forced 24 kHz one.
        assert film.evaluate("__film.ctx.sampleRate") == 24000
        assert film.kinds("ctx")[0]["sampleRate"] == 24000
        # S-3: getUserMedia went through the tap, with no flags, grants or device.
        assert film.kinds("gum"), film._seen()
        assert not any("fake-device" in a for a in CHROMIUM_ARGS)
        assert film.errors == []

        began = film.evaluate("__film.beginTake()")
        film.page.wait_for_timeout(500)  # past the 100 ms sync mark, before T1
        d1 = _load(film, "t1", t1)
        d2 = _load(film, "t2", t2)
        assert d1 == pytest.approx(1.5, abs=0.01)
        assert d2 == pytest.approx(0.8, abs=0.01)
        film.evaluate("__film.playCaller('t1', null)")
        film.page.wait_for_timeout(1000)  # T1 is 1.5 s long; the agent chunk lands at ~4 s
        chunk = film.wait_event("chunk", timeout_s=15)
        # S-7: schedule T2 at first chunk + 1.5 s.
        wanted = chunk["t_received"] + 1500
        film.evaluate("([at]) => __film.playCaller('t2', at)", [wanted])
        caller2 = [c for c in film.kinds("caller") if c["id"] == "t2"][0]
        assert abs(caller2["t"] - wanted) <= 50, (caller2["t"], wanted)
        film.page.wait_for_timeout(2600)  # T2 ends 0.8 s after its start
        mix = _decode_webm(film.evaluate("__film.endTake()"))
        agent_only = _decode_webm(film.evaluate("__film.endAgentTake()"))
        first_t1 = [c for c in film.kinds("caller") if c["id"] == "t1"][0]
        take_end = film.kinds("take")[-1]
        sync = film.kinds("sync")[0]

    # S-4: what the FakeSession received through the page's real microphone path.
    sent = b"".join(s.pcm for s in factory.sessions[0].sends if s.kind == "audio" and s.pcm)
    frames = _frames_db(sent)
    regions = _loud_regions(frames)
    assert len(regions) == 2, (regions, [round(f) for f in frames])
    for (a, b), want in zip(regions, (1.5, 0.8), strict=True):
        assert abs((b - a + 1) * FRAME_S - want) <= 0.2
    covered = set()
    for a, b in regions:
        covered.update(range(a - 1, b + 2))
    outside = [db for i, db in enumerate(frames) if i not in covered]
    assert outside and max(outside) <= SILENT_DB, max(outside)
    print(
        f"S-4: mic regions {[(b - a + 1) * FRAME_S for a, b in regions]} s, "
        f"loudest outside {max(outside):.0f} dBFS, loudest inside {max(frames):.1f} dBFS"
    )
    print(f"S-7: T2 scheduled-vs-logged {caller2['t'] - wanted:+.1f} ms")

    # S-5: the take blob decodes; T1 and the agent chunk are in it; its length matches.
    span_s = (take_end["t"] - began) / 1000
    assert abs(len(mix) / 2 / RATE - span_s) <= 0.2, (len(mix) / 2 / RATE, span_s)
    t1_at = (first_t1["t"] - began) / 1000
    assert _rms_db(mix, t1_at + 0.15, t1_at + 1.35) >= LOUD_DB
    chunk_at = (chunk["start"] - began) / 1000
    chunk_len = (chunk["end"] - chunk["start"]) / 1000
    assert _rms_db(mix, chunk_at + 0.15, chunk_at + chunk_len - 0.15) >= LOUD_DB
    assert _rms_db(agent_only, chunk_at + 0.15, chunk_at + chunk_len - 0.15) >= LOUD_DB
    assert _rms_db(agent_only, t1_at + 0.15, t1_at + 1.35) <= SILENT_DB  # agent tap has no caller
    print(
        f"S-5: tap {len(mix) / 2 / RATE:.3f}s vs span {span_s:.3f}s; "
        f"T1 {_rms_db(mix, t1_at + 0.15, t1_at + 1.35):.1f} dBFS, "
        f"chunk {_rms_db(mix, chunk_at + 0.15, chunk_at + chunk_len - 0.15):.1f} dBFS"
    )
    beep = _frames_db(mix[: int(RATE * 0.6) * 2])
    onset = next((i for i, db in enumerate(beep) if db >= LOUD_DB), None)
    assert onset is not None, "sync beep not found in the tap"
    print(
        f"S-8 (fake): beep onset in tap {onset * FRAME_S:.3f}s, "
        f"logged {(sync['beep_at'] - began) / 1000:.3f}s"
    )


@pytest.mark.live
def test_spike_live_barge_in(tmp_path: Path) -> None:
    """S-4 (live), S-6, S-7, S-8 against the real Realtime API. Spends credits."""
    import asyncio

    import httpx

    from factory.composition import BOSON_API_BASE_URL, build_app
    from factory.gate.tts_boson import BosonTts

    env = _live_env()
    if not env.get("BOSON_API_KEY") or not env.get("ANTHROPIC_API_KEY"):
        pytest.fail("BOSON_API_KEY and ANTHROPIC_API_KEY must be set (env or .env)")

    async def synth() -> tuple[bytes, bytes]:
        async with httpx.AsyncClient(base_url=BOSON_API_BASE_URL, timeout=60) as http:
            tts = BosonTts(http, env["BOSON_API_KEY"])
            return (
                await tts.synthesise(
                    "Hi there. Can you tell me everything you can help me with?", "chloe"
                ),
                await tts.synthesise("Sorry, stop. I have a different question.", "chloe"),
            )

    t1, t2 = asyncio.run(synth())
    app = create_web_app(build_app(env, tmp_path))
    video_dir = tmp_path / "video"
    with _serve(app) as base, _chromium(base, video_dir) as film:
        _start_live(film)
        began = film.evaluate("__film.beginTake()")
        film.page.wait_for_timeout(500)
        _load(film, "t1", t1)
        _load(film, "t2", t2)
        film.evaluate("__film.playCaller('t1', null)")
        # S-4 (live): the agent answers T1.
        film.wait_event("ttfa", timeout_s=30)
        chunk = film.wait_event("chunk", timeout_s=30)
        wanted = chunk["t_received"] + 1500
        film.evaluate("([at]) => __film.playCaller('t2', at)", [wanted])
        caller2 = [c for c in film.kinds("caller") if c["id"] == "t2"][0]
        # S-7
        assert abs(caller2["t"] - wanted) <= 50, (caller2["t"], wanted)
        # S-6: the product reacts to T2.
        film.wait_event("speech_started", timeout_s=20)
        film.page.wait_for_timeout(2500)
        stops = film.kinds("stop")
        chunks = film.kinds("chunk")
        agent_only = _decode_webm(film.evaluate("__film.endAgentTake()"))
        mix = _decode_webm(film.evaluate("__film.endTake()"))
        sync = film.kinds("sync")[0]
        page_video = film.page.video
        film.page.close()
        video_path = page_video.path() if page_video else None

    # S-8 (measured, not a gate): the sync mark in the video and in the tap.
    beep = _frames_db(mix[: int(RATE * 0.6) * 2])
    onset = next((i for i, db in enumerate(beep) if db >= LOUD_DB), None)
    black = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(video_path),
            "-vf",
            "blackdetect=d=0.05:pic_th=0.9",
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stderr
    marks = [ln for ln in black.splitlines() if "black_start" in ln]
    print(
        f"S-8: sync perf t={sync['t']:.0f} ms, take began {began:.0f} ms, beep logged at "
        f"{sync['beep_at']:.0f} ms, beep onset in tap {None if onset is None else onset * FRAME_S}s"
    )
    print(f"S-8: blackdetect lines (video time): {marks}")

    assert stops, "the page never stopped a scheduled chunk after speech_started"

    # Last effective chunk end: each chunk ends at its scheduled end or at its stop, if earlier.
    def effective_end(chunk: dict[str, Any]) -> float:
        # Context-clock conversions drift by a few ms between events; match stops by start.
        stopped = [x["stop_at"] for x in stops if abs(x["start"] - chunk["start"]) < 20]
        return min([chunk["end"], *stopped])

    effective = max(effective_end(c) for c in chunks)
    after = (effective - began) / 1000 + 0.1
    level = _rms_db(agent_only, after, after + 0.3)
    print(
        f"S-6: effective chunk end {(effective - began) / 1000:.3f}s; "
        f"level after +100ms {level:.1f} dBFS"
    )
    assert level <= -50.0
