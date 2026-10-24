"""Ports: what the gate needs from the outside world, plus the domain events it consumes.

No vendor SDK is imported here. Adapters implement these; tests use doubles.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from factory.agent_spec.models import AgentSpec, Rubric

if TYPE_CHECKING:
    from factory.gate.records import EvalCard

Clock = Callable[[], float]
DEFAULT_CLOCK: Clock = time.monotonic


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AudioDelta:
    response_id: str
    nbytes: int
    t: float


@dataclass(frozen=True)
class TranscriptDelta:
    response_id: str
    text: str
    t: float


@dataclass(frozen=True)
class ResponseCreated:
    response_id: str
    t: float


@dataclass(frozen=True)
class ResponseDone:
    response_id: str
    status: str
    usage: Usage | None
    t: float


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    executor: Literal["client", "server"]
    t: float


@dataclass(frozen=True)
class SpeechStarted:
    t: float


@dataclass(frozen=True)
class SpeechStopped:
    t: float


@dataclass(frozen=True)
class SessionEnded:
    cause: Literal["quota refused", "idle timeout", "concurrency limit", "closed"]
    close_code: int | None
    error_text: str | None
    t: float


@dataclass(frozen=True)
class OtherEvent:
    type: str
    t: float


SessionEvent = (
    ResponseCreated
    | AudioDelta
    | TranscriptDelta
    | ResponseDone
    | ToolCall
    | SpeechStarted
    | SpeechStopped
    | SessionEnded
    | OtherEvent
)


class SessionRefused(Exception):
    """The server refused the session configuration (F7, F14)."""

    def __init__(self, error_text: str) -> None:
        super().__init__(error_text)
        self.error_text = error_text


class TtsError(Exception):
    """Text-to-speech synthesis failed."""


class TtsRateLimited(TtsError):
    """TTS answered 429 (F26: no Retry-After). A `TtsError`, so callers that do not retry are
    unchanged."""


class RealtimeSession(Protocol):
    async def open(self, spec: AgentSpec) -> None: ...

    async def send_audio(self, pcm: bytes) -> float:
        """Send one input_audio_buffer.append; returns the monotonic send time."""
        ...

    async def send_tool_output(self, call_id: str, output: str) -> None: ...

    def events(self) -> AsyncIterator[SessionEvent]: ...

    async def close(self) -> None: ...


SessionFactory = Callable[[], RealtimeSession]


class TtsPort(Protocol):
    async def synthesise(self, text: str, voice: str) -> bytes:
        """24 kHz s16le mono PCM (F22). Raises `TtsError`."""
        ...


@dataclass(frozen=True)
class JudgeRequest:
    rubric: Rubric
    user_turns: list[str]
    transcript: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class JudgePort(Protocol):
    async def judge(self, request: JudgeRequest) -> str: ...


class BriefModel(Protocol):
    async def draft_spec(self, brief: str) -> str: ...


class CoachModel(Protocol):
    async def rewrite_procedure(self, prompt: str) -> str: ...


class CardStorePort(Protocol):
    def save(self, card: "EvalCard") -> Path: ...

    def latest(self, agent_id: str) -> "EvalCard | None": ...


class AvatarError(Exception):
    """The avatar could not start or stay up. The message is safe to show: no keys, no tokens."""


@dataclass(frozen=True)
class AvatarInfo:
    """What the browser may know: where the room is and a subscribe-only, short-lived token."""

    url: str
    room: str
    viewer_token: str
    avatar_identity: str


class AvatarPort(Protocol):
    """One realtime avatar session (F11): assistant PCM in, video and audio out through a room."""

    @property
    def info(self) -> AvatarInfo: ...

    async def audio(self, pcm: bytes) -> None:
        """24 kHz s16le mono assistant PCM (F11). Raises `AvatarError` when the avatar is down."""
        ...

    async def clear(self) -> None:
        """Barge-in: drop what the avatar has not yet spoken."""
        ...

    async def flush(self) -> None:
        """End of one assistant response: close the audio stream."""
        ...

    async def close(self) -> None:
        """End the avatar session and leave the room; never raises."""
        ...


AvatarFactory = Callable[[], Awaitable[AvatarPort]]
