"""Test doubles for the ports in `factory.ports`."""

import asyncio
import copy
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from factory.agent_spec.models import AgentSpec
from factory.ports import Clock, SessionEvent, SessionRefused, TtsError


@dataclass(frozen=True)
class Delay:
    """Script item: pause the event stream for `seconds`."""

    seconds: float


@dataclass(frozen=True)
class Refuse:
    """Script item: `open()` raises `SessionRefused(error_text)` (F7, F14)."""

    error_text: str


@dataclass(frozen=True)
class Sent:
    kind: Literal["audio", "tool_output"]
    t: float
    pcm: bytes | None = None
    call_id: str | None = None
    output: str | None = None


class FakeSession:
    def __init__(
        self,
        script: list[SessionEvent | Delay | Refuse] | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self.script = list(script or [])
        self.clock = clock
        self.open_calls = 0
        self.closed = False
        self.sends: list[Sent] = []

    async def open(self, spec: AgentSpec) -> None:
        self.open_calls += 1
        for item in self.script:
            if isinstance(item, Refuse):
                raise SessionRefused(item.error_text)

    async def send_audio(self, pcm: bytes) -> float:
        t = self.clock()
        self.sends.append(Sent("audio", t, pcm=pcm))
        return t

    async def send_tool_output(self, call_id: str, output: str) -> None:
        self.sends.append(Sent("tool_output", self.clock(), call_id=call_id, output=output))

    async def events(self) -> AsyncIterator[SessionEvent]:
        for item in self.script:
            if isinstance(item, Delay):
                await asyncio.sleep(item.seconds)
            elif isinstance(item, Refuse):
                continue
            else:
                yield item

    async def close(self) -> None:
        self.closed = True


class FakeSessionFactory:
    def __init__(
        self,
        script: list[SessionEvent | Delay | Refuse] | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self.script = script
        self.clock = clock
        self.calls = 0
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        self.calls += 1
        session = FakeSession(self.script, self.clock)
        self.sessions.append(session)
        return session


class FakeTts:
    def __init__(self, fail_texts: set[str] | None = None, pcm: bytes = b"\x01\x00" * 2400) -> None:
        self.fail_texts = fail_texts or set()
        self.pcm = pcm
        self.requests: list[tuple[str, str]] = []

    async def synthesise(self, text: str, voice: str) -> bytes:
        self.requests.append((text, voice))
        if text in self.fail_texts:
            raise TtsError(f"fake TTS failure for {text!r}")
        return self.pcm


class FakeJudge:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.requests: list[Any] = []

    async def judge(self, request: Any) -> str:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("FakeJudge has no reply left")
        return self.replies.pop(0)


class FakeBriefModel:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0
        self.briefs: list[str] = []

    async def draft_spec(self, brief: str) -> str:
        self.calls += 1
        self.briefs.append(brief)
        return self.reply


_BASE_SPEC: dict[str, Any] = {
    "id": "agent-1",
    "schema_version": 1,
    "source": {"kind": "template", "template_id": "specialist-training"},
    "role": "Test agent",
    "instructions": "Answer in at most two sentences.",
    "voice": "default",
    "output_modality": "audio",
    "temperature": None,
    "max_output_tokens": 200,
    "tools": [],
    "turn_detection": {"threshold": 0.85, "prefix_padding_ms": 300, "silence_duration_ms": 500},
    "scenarios": [
        {
            "id": "s1",
            "title": "Greeting",
            "user_voice": "chloe",
            "user_turns": [{"text": "Hello there."}],
            "expected_tool_call": None,
            "rubric": {
                "pass_criteria": ["Greets the user"],
                "partial_criteria": ["Replies without a greeting"],
                "fail_criteria": ["Does not reply"],
            },
        }
    ],
    "budget": {
        "max_scenarios": 6,
        "max_audio_s_per_run": 240.0,
        "max_judge_calls_per_scenario": 1,
        "max_live_session_s": 180.0,
    },
}


def make_spec(**overrides: Any) -> dict[str, Any]:
    """A minimal valid raw Agent Spec; top-level keys in `overrides` replace the defaults."""
    spec = copy.deepcopy(_BASE_SPEC)
    spec.update(copy.deepcopy(overrides))
    return spec
