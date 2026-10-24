"""Ports of the film recorder: the browser page and the demo server's reads.

Events are frozen dataclasses with every time in seconds on the page clock (`performance.now()`
divided by 1000). The page adapter converts; the domain never sees milliseconds.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class Ready:
    t: float
    released: bool | None


@dataclass(frozen=True)
class SpeechStartedSignal:
    """The page received `speech_started` or `clear` and stops its playback (F15)."""

    t: float


@dataclass(frozen=True)
class TtfaShown:
    t: float
    ms: float
    label: str


@dataclass(frozen=True)
class TranscriptShown:
    t: float
    text: str


@dataclass(frozen=True)
class SessionEndedShown:
    t: float
    reason: str
    message: str


@dataclass(frozen=True)
class AssistantChunk:
    """One binary frame of assistant audio: received at `t_received`, scheduled to play from
    `start` to `end` on the page clock."""

    t_received: float
    start: float
    end: float


@dataclass(frozen=True)
class PlaybackStopped:
    """The page stopped every assistant source at `t` (barge-in or teardown)."""

    t: float


@dataclass(frozen=True)
class BannerShown:
    """The "not released" banner is visible."""

    t: float


@dataclass(frozen=True)
class CallerPlayed:
    t: float
    line_id: Literal["T1", "T2"]
    duration_s: float


@dataclass(frozen=True)
class RequestBlocked:
    t: float
    label: str


@dataclass(frozen=True)
class StatusShown:
    t: float
    text: str


PageEvent = (
    Ready
    | SpeechStartedSignal
    | TtfaShown
    | TranscriptShown
    | SessionEndedShown
    | AssistantChunk
    | PlaybackStopped
    | BannerShown
    | CallerPlayed
    | RequestBlocked
    | StatusShown
)


class PagePort(Protocol):
    """One browser page on the demo UI, with a fake microphone and a tap on what it plays."""

    async def open(self, base_url: str, video_path: Path | None) -> None: ...

    async def select_agent(self, agent_id: str) -> None: ...

    async def avatar_ticked(self) -> bool: ...

    async def show(self, target: str) -> None:
        """Scroll to and reveal a locator (beats 4-6)."""
        ...

    async def boxes(self, locators: Sequence[str]) -> dict[str, tuple[float, float, float, float]]:
        """Bounding boxes (x, y, w, h) in page pixels, keyed by locator."""
        ...

    async def sync_mark(self) -> float:
        """Flash the sync mark (picture and tap); returns its page-clock time in seconds."""
        ...

    async def load_caller(self, line_id: str, pcm: bytes) -> None: ...

    async def play_caller(self, line_id: str, at: float | None) -> None:
        """Play a caller stem into the microphone at page-clock `at` (None: now)."""
        ...

    async def begin_take(self) -> float: ...

    async def click_start(self) -> None: ...

    async def click_stop(self) -> None: ...

    async def click(self, selector: str) -> None: ...

    def events(self) -> AsyncIterator[PageEvent]: ...

    async def end_take(self, path: Path) -> None:
        """Write the take's audio track (webm) to `path`."""
        ...

    async def close(self) -> None: ...


PageFactory = Callable[[], Awaitable[PagePort]]


class ServerPort(Protocol):
    """Read-only questions to the demo server (GETs only)."""

    async def latest_run_id(self, agent_id: str) -> str | None: ...

    async def coach_pair(self, agent_id: str) -> tuple[str, str] | None:
        """(v1 run id, v2 run id) of the coach box, or None."""
        ...
