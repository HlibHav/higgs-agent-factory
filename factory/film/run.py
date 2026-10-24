"""Run orchestration: pre-take checks, page beats 4-6, then N takes (AC-1..AC-5, AC-16, AC-28,
AC-29, AC-39, AC-62, AC-63).

Service layer. The browser is a `PagePort`, the demo server a `ServerPort`; both are injected.
The run is event-driven: it polls what the page reported (page-clock seconds) with the injected
`sleep`, so tests drive it in virtual time. No live session opens before every pre-take check
has passed, and none opens during beats 4-6.
"""

import asyncio
import dataclasses
import hashlib
import json
import os
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from factory.film import page_port as pp
from factory.film.audio import StemRejected, check_t2
from factory.film.guard import RunRefused, check_base_url
from factory.film.line_data import LineData
from factory.film.page_port import (
    BannerShown,
    CallerPlayed,
    PageEvent,
    PageFactory,
    PagePort,
    RequestBlocked,
    ServerPort,
    SessionEndedShown,
    TranscriptShown,
)
from factory.film.stems import StemManifest, read_wav_pcm
from factory.film.take_log import TakeEntry, TakeLog, entry_from
from factory.film.takes import (
    NO_REPLY_S,
    judge_take,
    t1_at,
    t2_at,
    t2_reply_chunks,
)
from factory.film.timeline import (
    LEAD_S,
    TAIL_S,
    TAKE_POST_S,
    TAKE_PRE_S,
    TakeWindow,
    build_timeline,
    line_start_s,
)

__all__ = [
    "BRIEF_AGENT",
    "EXPECTED",
    "PretakeExpectations",
    "PretakeFailed",
    "RunConfig",
    "RunOutcome",
    "RunRefused",
    "ST_AGENT",
    "WallClock",
    "check_take_count",
    "load_take_events",
    "run_film",
    "save_take_events",
    "take_window",
]

Sleep = Callable[[float], Awaitable[None]]
WallClock = Callable[[], datetime]
T = TypeVar("T")

ST_AGENT = "specialist-training"  # the demo page's agent id for Specialist Training
POLL_S = 0.05
READY_TIMEOUT_S = 30.0
T2_REPLY_TIMEOUT_S = 30.0
REPLY_TAIL_S = 1.0  # AC-27 (assumed default): Stop 1.0 s after the T2 reply's last audio
TAKES_MIN, TAKES_MAX = 3, 5  # AC-16
RUN_ID_RE = r"^\d{8}T\d{6}Z-[0-9a-f]{6}$"
PAGE_BEATS = (4, 5, 6)


@dataclass(frozen=True)
class PretakeExpectations:
    st_latest: str
    coach: tuple[str, str]
    brief_agent: str
    brief_latest: str


# From the screenplay's "Before the take" (AC-2).
EXPECTED = PretakeExpectations(
    st_latest="20261024T180110Z-b501e4a3",
    coach=("20261024T174839Z-6f4ab3b5", "20261024T180110Z-b501e4a3"),
    brief_agent="brief-onboarding-buddy-b948ed",
    brief_latest="20261024T183254Z-a5b00df6",
)
BRIEF_AGENT = EXPECTED.brief_agent


class PretakeFailed(RunRefused):
    def __init__(self, check: str, detail: str) -> None:
        super().__init__(f"pre-take check failed: {check}: {detail}")
        self.check = check


@dataclass(frozen=True)
class RunConfig:
    base_url: str
    takes: int
    out_dir: Path
    results_dir: Path
    expected: PretakeExpectations = EXPECTED


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    entries: list[TakeEntry]
    stopped: str | None


def check_take_count(n: int) -> int:
    if not isinstance(n, int) or isinstance(n, bool) or not TAKES_MIN <= n <= TAKES_MAX:
        raise RunRefused(f"take count must be {TAKES_MIN} to {TAKES_MAX}, got {n!r}")
    return n


# --- event files -----------------------------------------------------------------------------

_EVENT_TYPES: dict[str, type] = {
    cls.__name__: cls
    for cls in (
        pp.Ready,
        pp.SpeechStartedSignal,
        pp.TtfaShown,
        pp.TranscriptShown,
        pp.SessionEndedShown,
        pp.AssistantChunk,
        pp.PlaybackStopped,
        pp.BannerShown,
        pp.CallerPlayed,
        pp.RequestBlocked,
        pp.StatusShown,
    )
}


def save_take_events(path: Path, t0: float, events: Sequence[PageEvent]) -> None:
    """`take-<n>.events.json`: the take's page events (JSON data) and the page time at which
    the take's audio track starts."""
    body = {
        "t0": t0,
        "events": [{"type": type(e).__name__, **dataclasses.asdict(e)} for e in events],
    }
    path.write_text(json.dumps(body, indent=1), encoding="utf-8")


def load_take_events(path: Path) -> tuple[float, list[PageEvent]]:
    body: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    events: list[PageEvent] = []
    for raw in body["events"]:
        fields = {k: v for k, v in raw.items() if k != "type"}
        events.append(_EVENT_TYPES[raw["type"]](**fields))
    return float(body["t0"]), events


def take_window(events: Sequence[PageEvent], t0: float) -> TakeWindow | None:
    """The kept stretch, in take-audio time: from 0.5 s before T1 to 0.8 s after the last audio
    of the reply to T2 (assumed default of the plan). None without T1 and T2."""
    t1 = next((e for e in events if isinstance(e, CallerPlayed) and e.line_id == "T1"), None)
    t2 = next((e for e in events if isinstance(e, CallerPlayed) and e.line_id == "T2"), None)
    if t1 is None or t2 is None:
        return None
    ends = [c.end for c in t2_reply_chunks(events, t2)]
    last_audio = max(ends) if ends else t2.t + t2.duration_s
    return TakeWindow(max(0.0, t1.t - TAKE_PRE_S - t0), last_audio + TAKE_POST_S - t0)


# --- helpers ---------------------------------------------------------------------------------


def _hash_tree(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if root.exists():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _snapshot(results_dir: Path) -> dict[str, str]:
    snap = _hash_tree(results_dir / "cards")
    snap.update(_hash_tree(results_dir / "agents"))
    return snap


def _latest_t(events: Sequence[PageEvent]) -> float:
    times = [getattr(e, "t", getattr(e, "t_received", 0.0)) for e in events]
    return max(times, default=0.0)


class _Collector:
    """Drains the page's event stream into a list; `wait` polls it with the injected sleep."""

    def __init__(self, page: PagePort, sleep: Sleep) -> None:
        self.events: list[PageEvent] = []
        self._sleep = sleep
        self._task = asyncio.create_task(self._drain(page))

    async def _drain(self, page: PagePort) -> None:
        async for event in page.events():
            self.events.append(event)

    def aborted(self) -> bool:
        return any(
            isinstance(e, RequestBlocked | BannerShown | SessionEndedShown) for e in self.events
        )

    async def wait(
        self, find: Callable[[Sequence[PageEvent]], T | None], timeout_s: float
    ) -> T | None:
        elapsed = 0.0
        while True:
            found = find(self.events)
            if found is not None:
                return found
            if self.aborted() or elapsed >= timeout_s:
                return None
            await self._sleep(POLL_S)
            elapsed += POLL_S

    async def close(self) -> None:
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)


def _blocked(events: Sequence[PageEvent]) -> str | None:
    hit = next((e for e in events if isinstance(e, RequestBlocked)), None)
    return None if hit is None else f"blocked: {hit.label}"


# --- the run ---------------------------------------------------------------------------------


class _Run:
    def __init__(
        self,
        cfg: RunConfig,
        page_factory: PageFactory,
        server: ServerPort,
        lines: LineData,
        manifest: StemManifest,
        clock: WallClock,
        sleep: Sleep,
    ) -> None:
        self.cfg = cfg
        self.page_factory = page_factory
        self.server = server
        self.lines = lines
        self.manifest = manifest
        self.clock = clock
        self.sleep = sleep
        self.durations = {r.line_id: r.duration_s for r in manifest.records}
        self.run_id = f"{clock():%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
        self.run_dir = cfg.out_dir / "runs" / self.run_id

    # -- pre-take checks (AC-2) --

    async def pretake(self) -> None:
        exp = self.cfg.expected
        try:
            latest = await self.server.latest_run_id(ST_AGENT)
        except Exception as exc:  # noqa: BLE001 - any failure of a read is "not reachable"
            raise PretakeFailed("server reachable", str(exc) or type(exc).__name__) from exc
        if latest != exp.st_latest:
            raise PretakeFailed(
                "latest card", f"{ST_AGENT} latest is {latest!r}, expected {exp.st_latest!r}"
            )
        pair = await self.server.coach_pair(ST_AGENT)
        if pair != exp.coach:
            raise PretakeFailed("coach pair", f"coach box shows {pair!r}, expected {exp.coach!r}")
        brief = await self.server.latest_run_id(exp.brief_agent)
        if brief != exp.brief_latest:
            raise PretakeFailed(
                "brief agent",
                f"{exp.brief_agent} latest is {brief!r}, expected {exp.brief_latest!r}",
            )
        page = await self.page_factory()
        try:
            await page.open(self.cfg.base_url, None)
            await page.select_agent(ST_AGENT)
            ticked = await page.avatar_ticked()
        finally:
            await page.close()
        if ticked:
            raise PretakeFailed("avatar unticked", "Avatar (optional) is ticked")
        self.check_stems()

    def check_stems(self) -> None:
        wanted = [n.id for b in self.lines.beats for n in b.narrator] + ["T1", "T2"]
        by_id = {r.line_id: r for r in self.manifest.records}
        missing = [
            line_id
            for line_id in wanted
            if line_id not in by_id
            or by_id[line_id].duration_s <= 0
            or not Path(by_id[line_id].path).is_file()
            or not Path(by_id[line_id].path).with_suffix(".json").is_file()
        ]
        if missing:
            raise PretakeFailed("stems cached", f"no cached stem with a duration for {missing}")

    def stem_pcm(self, line_id: str) -> bytes:
        record = next(r for r in self.manifest.records if r.line_id == line_id)
        return read_wav_pcm(Path(record.path))

    # -- page beats 4-6 (AC-39) --

    def beat_hold_s(self, number: int) -> float:
        beat = next(b for b in self.lines.beats if b.number == number)
        return LEAD_S + sum(self.durations[n.id] for n in beat.narrator) + TAIL_S

    async def page_beat(self, number: int) -> str | None:
        agent = BRIEF_AGENT if number == 6 else ST_AGENT
        page = await self.page_factory()
        col = _Collector(page, self.sleep)
        try:
            await page.open(self.cfg.base_url, self.run_dir / f"page-b{number}.video.webm")
            await page.select_agent(agent)
            await page.sync_mark()
            hold = self.beat_hold_s(number)
            spent = 0.0
            if number == 5:
                spent = await self.highlights(page)
            await self.sleep(max(0.0, hold - spent))
            await self.sleep(POLL_S)  # let the last events reach the collector
        finally:
            await col.close()
            await page.close()
        return _blocked(col.events)

    async def highlights(self, page: PagePort) -> float:
        """Show each highlight when its sentence starts and keep the boxes (AC-38)."""
        t = build_timeline(self.lines, self.durations, None)
        beat_start = t.beat(5).start_s or 0.0
        boxes: dict[str, list[float]] = {}
        spent = 0.0
        for h in sorted(self.lines.highlights, key=lambda x: line_start_s(t, x.at_line)):
            at = line_start_s(t, h.at_line) - beat_start
            if at > spent:
                await self.sleep(at - spent)
                spent = at
            await page.show(h.target)
            found = await page.boxes([h.target])
            if h.target in found:
                boxes[h.id] = list(found[h.target])
        (self.run_dir / "boxes-b5.json").write_text(json.dumps(boxes, indent=1), encoding="utf-8")
        return spent

    # -- one take --

    async def take(self, n: int) -> tuple[TakeEntry, str | None]:
        page = await self.page_factory()
        col = _Collector(page, self.sleep)
        started = self.clock()
        t1: CallerPlayed | None = None
        t2: CallerPlayed | None = None
        t0 = 0.0
        try:
            await page.open(self.cfg.base_url, self.run_dir / f"take-{n}.video.webm")
            await page.select_agent(ST_AGENT)
            await page.load_caller("T1", self.stem_pcm("T1"))
            await page.load_caller("T2", self.stem_pcm("T2"))
            t0 = await page.begin_take()
            intro = self.durations["b7-intro"]
            await self.sleep(LEAD_S + intro + TAIL_S)  # the intro plays over the take video
            await page.click_start()
            ready = await col.wait(
                lambda ev: next((e for e in ev if isinstance(e, pp.Ready)), None), READY_TIMEOUT_S
            )
            if ready is not None:
                await self.sleep(POLL_S)  # let a banner or an immediate end arrive
            if ready is not None and not col.aborted():
                t1, t2 = await self.talk(page, col, ready)
            await page.click_stop()
            await page.end_take(self.run_dir / f"take-{n}.webm")
        finally:
            await col.close()
            await page.close()
        save_take_events(self.run_dir / f"take-{n}.events.json", t0, col.events)
        verdict = judge_take(col.events, t1, t2)
        stop = verdict.stop_run
        blocked = _blocked(col.events)
        if blocked is not None:
            verdict = dataclasses.replace(
                verdict, status="dropped", reasons=[*verdict.reasons, blocked]
            )
            stop = blocked
        entry = entry_from(verdict, n, started)
        TakeLog(self.run_dir / "takes.jsonl").append(entry)
        return entry, stop

    async def talk(
        self, page: PagePort, col: _Collector, ready: pp.Ready
    ) -> tuple[CallerPlayed | None, CallerPlayed | None]:
        def played(line: str) -> Callable[[Sequence[PageEvent]], CallerPlayed | None]:
            return lambda ev: next(
                (e for e in ev if isinstance(e, CallerPlayed) and e.line_id == line), None
            )

        at = t1_at(ready)
        await page.play_caller("T1", at)
        wait_s = max(0.0, at - _latest_t(col.events)) + 3.0
        t1 = await col.wait(played("T1"), wait_s)
        if t1 is None:
            return None, None
        first = await col.wait(lambda ev: t2_at(ev, t1), t1.duration_s + NO_REPLY_S)
        if first is None:
            return t1, None
        # `first` is the T2 due time on the page clock. The page cancels T2 itself when no
        # assistant source is playing then (AC-20), so no CallerPlayed(T2) follows.
        await page.play_caller("T2", first)
        wait_s = max(0.0, first - _latest_t(col.events)) + 3.0
        t2 = await col.wait(played("T2"), wait_s)
        if t2 is None:
            return t1, None
        reply = await col.wait(
            lambda ev: next((e for e in ev if isinstance(e, TranscriptShown) and e.t > t2.t), None),
            T2_REPLY_TIMEOUT_S,
        )
        if reply is not None:
            last_end = max((c.end for c in t2_reply_chunks(col.events, t2)), default=0.0)
            await self.sleep(max(0.0, last_end - _latest_t(col.events)) + REPLY_TAIL_S)
        return t1, t2


def _acquire_lock(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RunRefused(
            f"another run is in progress (lock {path}); if none is, remove the lock by hand"
        ) from exc
    with os.fdopen(fd, "w") as fh:
        fh.write(str(os.getpid()))


async def run_film(
    cfg: RunConfig,
    *,
    page_factory: PageFactory,
    server: ServerPort,
    lines: LineData,
    manifest: StemManifest,
    clock: WallClock,
    sleep: Sleep,
) -> RunOutcome:
    lock = cfg.out_dir / "film-run.lock"
    _acquire_lock(lock)  # AC-63: before any live session and before the take log
    before: dict[str, str] | None = None
    entries: list[TakeEntry] = []
    stopped: str | None = None
    run: _Run | None = None
    try:
        check_take_count(cfg.takes)
        check_base_url(cfg.base_url)
        t2_record = next((r for r in manifest.records if r.line_id == "T2"), None)
        if t2_record is None:
            raise PretakeFailed("stems cached", "no T2 stem")
        try:
            check_t2(read_wav_pcm(Path(t2_record.path)), "T2")  # AC-15
        except StemRejected as exc:
            raise RunRefused(str(exc)) from exc
        run = _Run(cfg, page_factory, server, lines, manifest, clock, sleep)
        await run.pretake()
        before = _snapshot(cfg.results_dir)
        run.run_dir.mkdir(parents=True, exist_ok=True)
        for number in PAGE_BEATS:
            stopped = await run.page_beat(number)
            if stopped:
                break
        if stopped is None:
            for n in range(1, cfg.takes + 1):  # AC-62: exactly the requested number
                entry, stop = await run.take(n)
                entries.append(entry)
                if stop:
                    stopped = stop
                    break
    finally:
        after = _snapshot(cfg.results_dir)
        changed = (
            []
            if before is None
            else sorted(p for p in set(after) | set(before) if after.get(p) != before.get(p))
        )
        lock.unlink(missing_ok=True)
    if changed:
        note = f"stored records changed during the run: {changed}"
        stopped = note if stopped is None else f"{stopped}; {note}"
    assert run is not None
    return RunOutcome(run.run_id, entries, stopped)
