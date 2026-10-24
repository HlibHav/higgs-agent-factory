"""Run orchestration over scripted pages in virtual time (AC-2, AC-5, AC-16, AC-28, AC-29,
AC-39, AC-62, AC-63) and the request guard (AC-3, AC-4)."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factory.film.guard import RunRefused, blocked_label, check_base_url
from factory.film.line_data import LineData, load_lines
from factory.film.run import (
    EXPECTED,
    PretakeFailed,
    RunConfig,
    RunOutcome,
    check_take_count,
    load_take_events,
    run_film,
    take_window,
)
from factory.film.stems import StemManifest
from factory.film.take_log import TakeLog
from tests.film_doubles import (
    FakeServer,
    LoopbackPage,
    Scenario,
    Sim,
    build_manifest,
    fast_sleep,
    loopback_server,
)

LINES = load_lines()
NOW = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
BASE = "http://127.0.0.1:8000"


@pytest.fixture
def manifest(tmp_path: Path) -> StemManifest:
    return build_manifest(tmp_path / "stems-base", LINES)


def _cfg(tmp_path: Path, takes: int = 3, base_url: str = BASE) -> RunConfig:
    results = tmp_path / "results"
    (results / "cards" / "specialist-training").mkdir(parents=True, exist_ok=True)
    (results / "cards" / "specialist-training" / "c1.json").write_text('{"run_id": "c1"}')
    (results / "agents").mkdir(parents=True, exist_ok=True)
    (results / "agents" / "a1.json").write_text('{"id": "a1"}')
    return RunConfig(base_url, takes, tmp_path / "out", results)


def _run(
    cfg: RunConfig,
    sim: Sim,
    manifest: StemManifest,
    server: FakeServer | None = None,
    lines: LineData = LINES,
) -> RunOutcome:
    return asyncio.run(
        run_film(
            cfg,
            page_factory=sim.factory,
            server=server or FakeServer(),
            lines=lines,
            manifest=manifest,
            clock=lambda: NOW,
            sleep=sim.sleep,
        )
    )


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --- guard ---------------------------------------------------------------------------------


def test_blocked_label_for_six_routes() -> None:
    cases = {
        "/api/agents/x/gate": "gate run",
        "/api/agents/x/coach/run": "coach run",
        "/api/agents/x/scenarios/s/check": "single-scenario check",
        "/api/brief": "brief proposal",
        "/api/proposals/p/save": "proposal save",
        "/api/avatar/session": "avatar session",
    }
    for path, label in cases.items():
        assert blocked_label("POST", f"http://127.0.0.1:8000{path}") == label
        assert blocked_label("post", f"http://127.0.0.1:8000{path}?x=1") == label
        assert blocked_label("GET", f"http://127.0.0.1:8000{path}") is None
    assert blocked_label("POST", "http://127.0.0.1:8000/api/agents/x/card/latest") is None
    assert blocked_label("DELETE", "http://127.0.0.1:8000/api/avatar/session") is None


def test_base_url_must_be_loopback() -> None:
    for ok in ("http://127.0.0.1:8000", "http://localhost:8000/", "http://[::1]:8000"):
        assert check_base_url(ok)
    for bad in ("http://example.com", "http://10.0.0.5:8000", "ftp://127.0.0.1", "127.0.0.1:8000"):
        with pytest.raises(RunRefused):
            check_base_url(bad)


def test_run_refuses_a_non_loopback_base_url_before_any_page(
    tmp_path: Path, manifest: StemManifest
) -> None:
    sim = Sim()
    with pytest.raises(RunRefused, match="loopback"):
        _run(_cfg(tmp_path, base_url="http://example.com"), sim, manifest)
    assert sim.pages == []


# --- take count, pre-take checks, lock -----------------------------------------------------


def test_take_count_bounds(tmp_path: Path, manifest: StemManifest) -> None:
    for n in (3, 4, 5):
        assert check_take_count(n) == n
    for n in (0, 1, 2, 6, 10, -3):
        with pytest.raises(RunRefused, match="take count"):
            check_take_count(n)
    sim = Sim()
    with pytest.raises(RunRefused):
        _run(_cfg(tmp_path, takes=2), sim, manifest)
    assert sim.pages == [] and not (tmp_path / "out" / "film-run.lock").exists()


@pytest.mark.parametrize(
    ("server", "check"),
    [
        (FakeServer(latest={"specialist-training": "20261024T174839Z-6f4ab3b5"}), "latest card"),
        (FakeServer(pair=("a", "b")), "coach pair"),
        (FakeServer(pair=None), "coach pair"),
        (
            FakeServer(
                latest={"specialist-training": EXPECTED.st_latest, EXPECTED.brief_agent: "x"}
            ),
            "brief agent",
        ),
        (FakeServer(error=ConnectionError("down")), "server reachable"),
    ],
)
def test_pretake_checks_stop_before_live(
    tmp_path: Path, manifest: StemManifest, server: FakeServer, check: str
) -> None:
    sim = Sim()
    with pytest.raises(PretakeFailed) as info:
        _run(_cfg(tmp_path), sim, manifest, server)
    assert info.value.check == check and check in str(info.value)
    assert sim.started == 0
    assert not (tmp_path / "out" / "film-run.lock").exists()  # released
    assert not (tmp_path / "out" / "runs").exists()  # nothing written


def test_pretake_v1_latest_card_stops_before_live(tmp_path: Path, manifest: StemManifest) -> None:
    v1 = EXPECTED.coach[0]
    sim = Sim()
    server = FakeServer(
        latest={"specialist-training": v1, EXPECTED.brief_agent: EXPECTED.brief_latest}
    )
    with pytest.raises(PretakeFailed, match="latest card") as info:
        _run(_cfg(tmp_path), sim, manifest, server)
    assert v1 in str(info.value) and EXPECTED.st_latest in str(info.value)
    assert sim.started == 0 and all("click_start" not in p.calls for p in sim.pages)


def test_pretake_avatar_ticked_and_stems_missing(tmp_path: Path, manifest: StemManifest) -> None:
    sim = Sim(avatar_ticked=True)
    with pytest.raises(PretakeFailed, match="avatar unticked"):
        _run(_cfg(tmp_path), sim, manifest)
    assert sim.started == 0
    Path(manifest.records[3].path).unlink()
    with pytest.raises(PretakeFailed, match="stems cached") as info:
        _run(_cfg(tmp_path), Sim(), manifest)
    assert manifest.records[3].line_id in str(info.value)


def test_t2_stem_with_gap_refused_before_live(tmp_path: Path) -> None:
    from tests.film_doubles import silence_pcm, sine_pcm

    gappy = sine_pcm(0.5) + silence_pcm(0.6) + sine_pcm(0.3)
    # make_stems refuses a gappy T2, so build a clean manifest and swap the wav afterwards.
    manifest = build_manifest(tmp_path / "m", LINES)
    t2 = next(r for r in manifest.records if r.line_id == "T2")
    import wave

    with wave.open(t2.path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(gappy)
    sim = Sim()
    with pytest.raises(RunRefused, match="T2 has a 0.60 s silence"):
        _run(_cfg(tmp_path), sim, manifest)
    assert sim.started == 0


def test_second_run_refused_one_take_log(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=3)

    async def scenario() -> tuple[RunOutcome, Sim]:
        first = Sim()
        first.gate = asyncio.Event()
        task = asyncio.create_task(
            run_film(
                cfg,
                page_factory=first.factory,
                server=FakeServer(),
                lines=LINES,
                manifest=manifest,
                clock=lambda: NOW,
                sleep=first.sleep,
            )
        )
        while not (cfg.out_dir / "film-run.lock").exists():
            await asyncio.sleep(0.001)
        second = Sim()
        with pytest.raises(RunRefused, match="another run is in progress"):
            await run_film(
                cfg,
                page_factory=second.factory,
                server=FakeServer(),
                lines=LINES,
                manifest=manifest,
                clock=lambda: NOW,
                sleep=second.sleep,
            )
        assert second.pages == []  # the second run opened nothing
        first.gate.set()
        return await task, first

    outcome, _ = asyncio.run(scenario())
    logs = list((cfg.out_dir / "runs").glob("*/takes.jsonl"))
    assert len(logs) == 1 and len(logs[0].read_text().splitlines()) == 3
    assert [e.take for e in outcome.entries] == [1, 2, 3]
    assert not (cfg.out_dir / "film-run.lock").exists()


# --- the run -------------------------------------------------------------------------------


def test_four_takes_logged_even_after_candidate(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=4)
    outcome = _run(cfg, Sim(), manifest)
    assert outcome.stopped is None
    assert [e.take for e in outcome.entries] == [1, 2, 3, 4]
    assert [e.status for e in outcome.entries] == ["candidate"] * 4
    log = TakeLog(cfg.out_dir / "runs" / outcome.run_id / "takes.jsonl")
    assert [e.take for e in log.entries()] == [1, 2, 3, 4]
    first = outcome.entries[0]
    assert first.t2_offset_s == pytest.approx(1.5) and first.reasons == "none"
    assert first.t2_transcript.startswith("I can't share that")
    run_dir = cfg.out_dir / "runs" / outcome.run_id
    for n in range(1, 5):
        assert (run_dir / f"take-{n}.webm").exists()
        assert (run_dir / f"take-{n}.events.json").exists()


def test_events_file_round_trips_and_gives_a_take_window(
    tmp_path: Path, manifest: StemManifest
) -> None:
    cfg = _cfg(tmp_path, takes=3)
    outcome = _run(cfg, Sim(), manifest)
    t0, events = load_take_events(cfg.out_dir / "runs" / outcome.run_id / "take-1.events.json")
    window = take_window(events, t0)
    assert window is not None and 0 <= window.start_s < window.end_s
    assert take_window([], 0.0) is None


def test_no_live_session_during_page_beats(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=3)
    sim = Sim()
    outcome = _run(cfg, sim, manifest)
    started = [i for i, p in enumerate(sim.pages) if p.started]
    beat_pages = [p for p in sim.pages if p.video and "page-b" in p.video.name]
    assert [p.video.name for p in beat_pages if p.video] == [
        "page-b4.video.webm",
        "page-b5.video.webm",
        "page-b6.video.webm",
    ]
    assert not any(p.started for p in beat_pages)
    assert all("sync_mark" in p.calls for p in beat_pages)
    assert min(started) > max(sim.pages.index(p) for p in beat_pages)
    boxes = json.loads((cfg.out_dir / "runs" / outcome.run_id / "boxes-b5.json").read_text())
    assert set(boxes) == {h.id for h in LINES.highlights}
    shown = [c for c in beat_pages[1].calls if c.startswith("show:")]
    assert len(shown) == len(LINES.highlights)


def test_cards_byte_identical_after_full_and_early_stop(
    tmp_path: Path, manifest: StemManifest
) -> None:
    cfg = _cfg(tmp_path)
    before = _tree_hash(cfg.results_dir)
    full = _run(cfg, Sim(), manifest)
    assert full.stopped is None and _tree_hash(cfg.results_dir) == before
    early = _run(cfg, Sim([Scenario(ended=(1.0, "quota refused"))]), manifest)
    assert early.stopped == "quota refused" and _tree_hash(cfg.results_dir) == before


def test_a_changed_card_is_reported_in_the_outcome(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path)
    card = cfg.results_dir / "cards" / "specialist-training" / "c1.json"
    outcome = _run(cfg, Sim([Scenario(on_start=lambda: card.write_text("{}"))]), manifest)
    assert outcome.stopped is not None and "stored records changed" in outcome.stopped
    assert "c1.json" in outcome.stopped


def test_quota_refused_stops_run(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=5)
    outcome = _run(cfg, Sim([Scenario(ended=(1.0, "quota refused"))]), manifest)
    assert outcome.stopped == "quota refused"
    assert len(outcome.entries) == 1 and outcome.entries[0].status == "dropped"
    assert "quota refused" in outcome.entries[0].reasons


def test_not_released_banner_drops_and_stops(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=5)
    sim = Sim([Scenario(released=False)])
    outcome = _run(cfg, sim, manifest)
    assert outcome.stopped == "not released"
    assert len(outcome.entries) == 1
    assert outcome.entries[0].reasons == ["not released"]
    assert "play:T1" not in sim.pages[-1].calls  # nothing was spoken into a not-released agent


def test_gate_click_blocked_and_run_ends(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=5)
    outcome = _run(cfg, Sim([Scenario(blocked="gate run")]), manifest)
    assert outcome.stopped == "blocked: gate run"
    assert len(outcome.entries) == 1
    assert "blocked: gate run" in outcome.entries[0].reasons
    assert outcome.entries[0].status == "dropped"


def test_dropped_takes_do_not_stop_the_run(tmp_path: Path, manifest: StemManifest) -> None:
    cfg = _cfg(tmp_path, takes=3)
    scenarios = [Scenario(reply_len_s=0.6), Scenario(), Scenario(stops=False)]
    outcome = _run(cfg, Sim(scenarios), manifest)
    assert [e.status for e in outcome.entries] == ["dropped", "candidate", "dropped"]
    assert outcome.entries[0].reasons == ["T1 reply ended before T2"]
    assert outcome.entries[2].reasons == ["audio did not stop on T2"]
    assert outcome.stopped is None


# --- loopback: the real demo server on 127.0.0.1 ------------------------------------------

SIX = (
    ("POST", "/api/agents/specialist-training/gate"),
    ("POST", "/api/agents/specialist-training/coach/run"),
    ("POST", "/api/agents/specialist-training/scenarios/st-1/check"),
    ("POST", "/api/brief"),
    ("POST", "/api/proposals/p1/save"),
    ("POST", "/api/avatar/session"),
)


def _loopback_run(
    tmp_path: Path, manifest: StemManifest, base: str, pages: list[LoopbackPage], takes: int = 3
) -> RunOutcome:
    cfg = _cfg(tmp_path, takes=takes, base_url=base)

    async def factory() -> LoopbackPage:
        page = LoopbackPage(inject_on_open=None)
        pages.append(page)
        return page

    return asyncio.run(
        run_film(
            cfg,
            page_factory=factory,
            server=FakeServer(),
            lines=LINES,
            manifest=manifest,
            clock=lambda: NOW,
            sleep=fast_sleep(),
        )
    )


def test_run_sends_none_of_the_six_requests(tmp_path: Path, manifest: StemManifest) -> None:
    with loopback_server(tmp_path) as (base, log):
        pages: list[LoopbackPage] = []
        outcome = _loopback_run(tmp_path, manifest, base, pages, takes=3)
    assert outcome.stopped is None
    assert [e.status for e in outcome.entries] == ["candidate"] * 3
    for method, path in SIX:
        assert log.count(method, path) == 0, (method, path)
    assert not [i for i in log.items if i[1] == "POST"]
    assert log.count("GET", "/") >= 7  # the pages did load
    # AC-39: no WebSocket (live session) before the first take, exactly one per take after.
    assert len(log.websockets()) == 3
    first_ws = next(i for i, item in enumerate(log.items) if item[0] == "websocket")
    assert all(item[0] != "websocket" for item in log.items[:first_ws])
    beat_pages = [p for p in pages if p.video and "page-b" in p.video.name]
    assert len(beat_pages) == 3 and not any(p.started for p in beat_pages)


def test_loopback_gate_click_blocked_and_run_ends(tmp_path: Path, manifest: StemManifest) -> None:
    with loopback_server(tmp_path) as (base, log):
        cfg = _cfg(tmp_path, takes=5, base_url=base)

        async def factory() -> LoopbackPage:
            return LoopbackPage(inject_on_open="#gateBtn")

        outcome = asyncio.run(
            run_film(
                cfg,
                page_factory=factory,
                server=FakeServer(),
                lines=LINES,
                manifest=manifest,
                clock=lambda: NOW,
                sleep=fast_sleep(),
            )
        )
    assert outcome.stopped == "blocked: gate run"
    assert log.count("POST", "/api/agents/specialist-training/gate") == 0
    assert not log.websockets()  # the run ended during the page beats: no live session at all


def test_loopback_not_released_banner_drops_and_stops(
    tmp_path: Path, manifest: StemManifest
) -> None:
    with loopback_server(tmp_path, released=False) as (base, log):
        pages: list[LoopbackPage] = []
        outcome = _loopback_run(tmp_path, manifest, base, pages, takes=4)
    assert outcome.stopped == "not released"
    assert len(outcome.entries) == 1 and outcome.entries[0].reasons == ["not released"]
    assert len(log.websockets()) == 1
