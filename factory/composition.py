"""Composition root: builds the real adapters and wires them into the gate.

The only place that reads configuration and constructs adapters. Config comes from the
environment mapping passed in (never read here), and a key's value is never put in a message.

Boson facts: Realtime endpoint `wss://api.boson.ai/v1/realtime`, no `?model=` on the URL (F1);
the key goes in the handshake header only, which the session adapter sets (F23); TTS host
`https://api.boson.ai` (F22).
"""

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import anthropic
import httpx

from factory.agent_spec.brief_anthropic import AnthropicBriefModel
from factory.agent_spec.generator import BriefTooLong, generate_from_brief
from factory.agent_spec.models import AgentSpec, SpecIssue
from factory.agent_spec.templates import TemplateNotAvailable, load_template
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore
from factory.gate.judge_anthropic import AnthropicJudge
from factory.gate.records import EvalCard
from factory.gate.runner import GateAborted, GateRefused, preflight, run_gate
from factory.gate.tts_boson import BosonTts
from factory.gate.tts_cache import TurnAudioSource
from factory.ports import BriefModel, JudgePort, SessionFactory
from factory.runtime.boson_session import BosonRealtimeSession

BOSON_REALTIME_URL = "wss://api.boson.ai/v1/realtime"  # F1, F23
BOSON_API_BASE_URL = "https://api.boson.ai"  # F22
DEFAULT_JUDGE_MODEL = "claude-sonnet-5-5"  # ADR 2026-10-24-anthropic-sonnet-for-judge-and-generator
TEMPLATE_RECORDINGS_DIR = Path(__file__).parent / "agent_spec" / "templates" / "recordings"
TTS_TIMEOUT_S = 60.0


class ConfigError(Exception):
    """A required setting is missing. The message names the variable, never a value."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value.strip():
        raise ConfigError(f"{name} is not set; set it in the environment before running the gate")
    return value.strip()


@dataclass
class FactoryApp:
    sessions: SessionFactory
    audio: TurnAudioSource
    judge: JudgePort
    store: FileCardStore
    brief_model: BriefModel | None = None
    last_path: Path | None = None
    _closers: tuple[Callable[[], Awaitable[None]], ...] = ()

    async def run_gate_for_template(self, template_id: str) -> EvalCard | GateAborted:
        try:
            spec = load_template(template_id)
        except TemplateNotAvailable as exc:
            return GateAborted(f"Template unavailable: {exc}.")
        return await self._gate(spec)

    async def run_gate_for_brief(self, brief: str) -> EvalCard | GateAborted | list[SpecIssue]:
        if self.brief_model is None:
            return GateAborted("No brief model is configured.")
        try:
            generated = await generate_from_brief(brief, self.brief_model)
        except BriefTooLong as exc:
            return GateAborted(f"{exc}")
        except anthropic.APIError as exc:
            return GateAborted(f"The brief model call failed ({_api_error(exc)}).")
        if isinstance(generated, list):
            return generated
        return await self._gate(generated)

    async def _gate(self, spec: AgentSpec) -> EvalCard | GateAborted:
        try:
            checked = preflight(spec.model_dump(mode="json"))
            record = await run_gate(
                checked, sessions=self.sessions, audio=self.audio, judge=self.judge
            )
        except GateRefused as exc:
            return GateAborted(f"The gate refused to start: {exc}.")
        except GateAborted as exc:
            return GateAborted(f"{exc.error_text}")
        except anthropic.APIError as exc:
            return GateAborted(f"The judge call failed ({_api_error(exc)}); no verdict.")
        card = build_card(record)
        self.last_path = self.store.save(card)
        return card

    async def aclose(self) -> None:
        for closer in self._closers:
            await closer()


def _api_error(exc: anthropic.APIError) -> str:
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}, status {status}" if status else type(exc).__name__


def build_app(env: Mapping[str, str], results_dir: Path) -> FactoryApp:
    """Fails with `ConfigError` before any network call when a key is missing."""
    boson_key = _required(env, "BOSON_API_KEY")
    anthropic_key = _required(env, "ANTHROPIC_API_KEY")
    judge_model = env.get("FACTORY_JUDGE_MODEL", "").strip() or DEFAULT_JUDGE_MODEL

    http = httpx.AsyncClient(base_url=BOSON_API_BASE_URL, timeout=TTS_TIMEOUT_S)
    llm = anthropic.AsyncAnthropic(api_key=anthropic_key, max_retries=0)  # NFR: no retries
    return FactoryApp(
        sessions=lambda: BosonRealtimeSession(BOSON_REALTIME_URL, boson_key, time.monotonic),
        audio=TurnAudioSource(
            BosonTts(http, boson_key), results_dir / "tts-cache", TEMPLATE_RECORDINGS_DIR
        ),
        judge=AnthropicJudge(llm, model_id=judge_model),
        store=FileCardStore(results_dir / "cards"),
        brief_model=AnthropicBriefModel(llm, model_id=judge_model),
        _closers=(http.aclose, llm.close),
    )
