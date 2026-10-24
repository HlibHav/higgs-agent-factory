"""Composition root: builds the real adapters and wires them into the gate.

The only place that reads configuration and constructs adapters. Config comes from the
environment mapping passed in, or the process environment when none is given, and a key's
value is never put in a message.

Boson facts: Realtime endpoint `wss://api.boson.ai/v1/realtime`, no `?model=` on the URL (F1);
the key goes in the handshake header only, which the session adapter sets (F23); TTS host
`https://api.boson.ai` (F22).
"""

import base64
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import httpx

from factory.agent_spec.brief_anthropic import AnthropicBriefModel
from factory.agent_spec.generator import BriefTooLong, generate_from_brief
from factory.agent_spec.models import AgentSpec, SpecIssue
from factory.agent_spec.templates import TEMPLATE_IDS, TemplateNotAvailable, load_template
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore
from factory.gate.judge_anthropic import AnthropicJudge
from factory.gate.records import EvalCard
from factory.gate.runner import GateAborted, GateRefused, preflight, run_gate
from factory.gate.tts_boson import BosonTts
from factory.gate.tts_cache import TurnAudioSource
from factory.live.session import LiveAudioDelta
from factory.ports import (
    AudioDelta,
    BriefModel,
    JudgePort,
    RealtimeSession,
    SessionEvent,
    SessionFactory,
)
from factory.runtime.boson_session import BosonRealtimeSession

BOSON_REALTIME_URL = "wss://api.boson.ai/v1/realtime"  # F1, F23
BOSON_API_BASE_URL = "https://api.boson.ai"  # F22
DEFAULT_JUDGE_MODEL = "claude-sonnet-5-5"  # ADR 2026-10-24-anthropic-sonnet-for-judge-and-generator
TEMPLATE_RECORDINGS_DIR = Path(__file__).parent / "agent_spec" / "templates" / "recordings"
TTS_TIMEOUT_S = 60.0


_ACRONYMS = {"ai": "AI"}


class ConfigError(Exception):
    """A required setting is missing. The message names the variable, never a value."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value.strip():
        raise ConfigError(f"{name} is not set; set it in the environment before running the gate")
    return value.strip()


class LiveBosonSession(BosonRealtimeSession):
    """The gate's session adapter, with each audio delta also carrying its decoded PCM (F17)."""

    def _map(self, event: dict[str, Any], kind: Any, t: float) -> list[SessionEvent]:
        mapped = super()._map(event, kind, t)
        if kind != "response.output_audio.delta":
            return mapped
        live: list[SessionEvent] = []
        for item in mapped:
            if isinstance(item, AudioDelta):  # the base class already validated the base64
                pcm = base64.b64decode(event.get("delta") or "")
                item = LiveAudioDelta(item.response_id, item.nbytes, item.t, pcm=pcm)
            live.append(item)
        return live


class CheckFailed(Exception):
    """A single-scenario check produced no judgment; the text is safe to show."""


@dataclass(frozen=True)
class TemplateCard:
    template_id: str
    name: str
    description: str
    source_url: str | None
    available: bool


@dataclass(frozen=True)
class SingleCheck:
    """AC-53: one scenario run outside the gate. Never stored, never a verdict."""

    scenario_id: str
    label: str
    rationale: str
    evidence: str
    ttfa_ms: float | None
    stored_verdict: str | None


@dataclass
class FactoryApp:
    sessions: SessionFactory
    audio: TurnAudioSource
    judge: JudgePort
    store: FileCardStore
    brief_model: BriefModel | None = None
    last_path: Path | None = None
    live_sessions: SessionFactory | None = None  # live pages need PCM in the audio deltas
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

    # --- demo page (P2) ----------------------------------------------------------------

    def list_templates(self) -> list[TemplateCard]:
        """Every template in the registry, loadable or not (AC-38)."""
        cards = []
        for template_id in TEMPLATE_IDS:
            name = " ".join(_ACRONYMS.get(w, w.capitalize()) for w in template_id.split("-"))
            try:
                description, available = load_template(template_id).role, True
            except TemplateNotAvailable:
                description, available = "Card text pending.", False
            cards.append(TemplateCard(template_id, name, description, None, available))
        return cards

    def agent_spec(self, agent_id: str) -> AgentSpec | None:
        """The spec whose id is `agent_id`; only templates are persisted."""
        for template_id in TEMPLATE_IDS:
            try:
                spec = load_template(template_id)
            except TemplateNotAvailable:
                continue
            if spec.id == agent_id:
                return spec
        return None

    def latest_card(self, agent_id: str) -> EvalCard | None:
        try:
            return self.store.latest(agent_id)
        except ValueError:  # an id that cannot be a card directory
            return None

    def new_live_session(self) -> RealtimeSession:
        return (self.live_sessions or self.sessions)()

    async def run_single_scenario(self, agent_id: str, scenario_id: str) -> SingleCheck:
        """AC-53: run one scenario through the gate runner and judge; nothing is stored."""
        spec = self.agent_spec(agent_id)
        if spec is None:
            raise KeyError(agent_id)
        scenario = next((s for s in spec.scenarios if s.id == scenario_id), None)
        if scenario is None:
            raise KeyError(scenario_id)
        stored = self.latest_card(agent_id)
        try:
            checked = preflight(
                spec.model_copy(update={"scenarios": [scenario]}).model_dump(mode="json")
            )
            record = await run_gate(
                checked, sessions=self.sessions, audio=self.audio, judge=self.judge
            )
        except GateRefused as exc:
            raise CheckFailed(f"The check refused to start: {exc}.") from exc
        except GateAborted as exc:
            raise CheckFailed(exc.error_text) from exc
        except anthropic.APIError as exc:
            raise CheckFailed(f"The judge call failed ({_api_error(exc)}).") from exc
        judgment = record.scenarios[0].judgment if record.scenarios else None
        if judgment is None:
            reason = record.cause or "no judgment"
            raise CheckFailed(f"The check is incomplete ({reason}); no result.")
        ttfa = next((t.ttfa_ms for t in record.turns if t.ttfa_ms is not None), None)
        return SingleCheck(
            scenario_id=scenario_id,
            label=judgment.label,
            rationale=judgment.rationale,
            evidence=judgment.evidence,
            ttfa_ms=ttfa,
            stored_verdict=None if stored is None else stored.verdict,
        )

    async def aclose(self) -> None:
        for closer in self._closers:
            await closer()


def _api_error(exc: anthropic.APIError) -> str:
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}, status {status}" if status else type(exc).__name__


def build_app(env: Mapping[str, str] | None, results_dir: Path) -> FactoryApp:
    """Fails with `ConfigError` before any network call when a key is missing."""
    env = os.environ if env is None else env
    boson_key = _required(env, "BOSON_API_KEY")
    anthropic_key = _required(env, "ANTHROPIC_API_KEY")
    judge_model = env.get("FACTORY_JUDGE_MODEL", "").strip() or DEFAULT_JUDGE_MODEL

    http = httpx.AsyncClient(base_url=BOSON_API_BASE_URL, timeout=TTS_TIMEOUT_S)
    llm = anthropic.AsyncAnthropic(api_key=anthropic_key, max_retries=0)  # NFR: no retries
    return FactoryApp(
        sessions=lambda: BosonRealtimeSession(BOSON_REALTIME_URL, boson_key, time.monotonic),
        live_sessions=lambda: LiveBosonSession(BOSON_REALTIME_URL, boson_key, time.monotonic),
        audio=TurnAudioSource(
            BosonTts(http, boson_key), results_dir / "tts-cache", TEMPLATE_RECORDINGS_DIR
        ),
        judge=AnthropicJudge(llm, model_id=judge_model),
        store=FileCardStore(results_dir / "cards"),
        brief_model=AnthropicBriefModel(llm, model_id=judge_model),
        _closers=(http.aclose, llm.close),
    )
