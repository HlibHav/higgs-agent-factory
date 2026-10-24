"""Composition root: builds the real adapters and wires them into the gate.

The only place that reads configuration and constructs adapters. Config comes from the
environment mapping passed in, or the process environment when none is given, and a key's
value is never put in a message.

Boson facts: Realtime endpoint `wss://api.boson.ai/v1/realtime`, no `?model=` on the URL (F1);
the key goes in the handshake header only, which the session adapter sets (F23); TTS host
`https://api.boson.ai` (F22).
"""

import base64
import json
import os
import re
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic
import httpx

from factory.agent_spec.brief_anthropic import AnthropicBriefModel
from factory.agent_spec.generator import BriefTooLong, generate_from_brief
from factory.agent_spec.models import AgentSpec, ClientTool, SpecIssue
from factory.agent_spec.templates import TEMPLATE_IDS, TemplateNotAvailable, load_template
from factory.agent_spec.validation import validate_agent_spec
from factory.coach.coach import coach_spec
from factory.coach.coach_anthropic import AnthropicCoachModel
from factory.film.app import FilmApp
from factory.film.browser_playwright import open_playwright_page
from factory.film.ffmpeg import Ffmpeg
from factory.film.server_http import HttpServer
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore
from factory.gate.judge_anthropic import AnthropicJudge
from factory.gate.records import EvalCard
from factory.gate.runner import GateAborted, GateRefused, preflight, run_gate
from factory.gate.tts_boson import TTS_MODEL, BosonTts
from factory.gate.tts_cache import TurnAudioSource
from factory.live.session import LiveAudioDelta
from factory.ports import (
    AudioDelta,
    AvatarFactory,
    BriefModel,
    CoachModel,
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
AVATAR_MAX_DURATION_S = 600  # F11: ends at expires_at even if we never delete it


_ACRONYMS = {"ai": "AI"}


_BRIEF_ID = re.compile(r"brief-[a-z0-9-]{1,48}")


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
    coach_model: CoachModel | None = None
    last_path: Path | None = None
    live_sessions: SessionFactory | None = None  # live pages need PCM in the audio deltas
    avatar: AvatarFactory | None = None  # None: avatar not configured (LIVEKIT_* unset)
    agents_dir: Path | None = None  # saved brief agents (AC-81); None: none can be saved
    _closers: tuple[Callable[[], Awaitable[None]], ...] = ()

    async def run_gate_for_template(
        self, template_id: str, caller_voice: str | None = None
    ) -> EvalCard | GateAborted:
        try:
            spec = load_template(template_id)
        except TemplateNotAvailable as exc:
            return GateAborted(f"Template unavailable: {exc}.")
        return await self._gate(spec, caller_voice=caller_voice)

    async def coach_template(
        self,
        template_id: str,
        rounds: int = 2,
        from_latest: bool = True,
        caller_voice: str | None = None,
    ) -> list[EvalCard] | GateAborted:
        """AC-76, AC-77: gate, then coach and re-gate while rejected. Each card's verdict is
        its own gate's verdict; the coach never sets it."""
        template = self._base_spec(template_id)
        if template is None:
            return GateAborted(f"Unknown agent: {template_id}.")
        if self.coach_model is None:
            return GateAborted("No coach model is configured.")
        first: EvalCard | GateAborted | None = None
        if from_latest:
            stored = self.latest_card(template.id)
            if stored is not None and stored.verdict == "rejected" and stored.agent_spec:
                first = stored
        if first is None:
            first = await self._gate(template, caller_voice=caller_voice)
        if isinstance(first, GateAborted):
            return first
        cards = [first]
        for _ in range(max(rounds, 0)):
            latest = cards[-1]
            if latest.verdict != "rejected" or not latest.agent_spec:
                break
            current = validate_agent_spec(latest.agent_spec)
            if not isinstance(current, AgentSpec):
                break
            try:
                coached = await coach_spec(current, latest, self.coach_model)
            except anthropic.APIError as exc:
                return GateAborted(f"The coach call failed ({_api_error(exc)}).")
            if coached is None:
                break
            new_spec, changed = coached
            result = await self._gate(
                new_spec,
                caller_voice=caller_voice,
                parent_run_id=latest.run_id,
                coach_note=f"coach rewrote: {', '.join(changed)}",
            )
            if isinstance(result, GateAborted):
                return result
            cards.append(result)
        return cards

    def coach_pair(self, agent_id: str) -> tuple[EvalCard, EvalCard] | None:
        """The latest card that has a parent, and that parent."""
        latest = self.latest_card(agent_id)
        if latest is None or latest.parent_run_id is None:
            return None
        try:
            parent = self.store.by_run_id(agent_id, latest.parent_run_id)
        except ValueError:
            return None
        return None if parent is None else (parent, latest)

    async def run_gate_for_brief(
        self, brief: str, caller_voice: str | None = None
    ) -> EvalCard | GateAborted | list[SpecIssue]:
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
        return await self._gate(generated, caller_voice=caller_voice)

    async def _gate(
        self,
        spec: AgentSpec,
        caller_voice: str | None = None,
        parent_run_id: str | None = None,
        coach_note: str | None = None,
    ) -> EvalCard | GateAborted:
        try:
            checked = preflight(spec.model_dump(mode="json"))
            record = await run_gate(
                checked,
                sessions=self.sessions,
                audio=self.audio,
                judge=self.judge,
                caller_voice=caller_voice,
            )
        except GateRefused as exc:
            return GateAborted(f"The gate refused to start: {exc}.")
        except GateAborted as exc:
            return GateAborted(f"{exc.error_text}")
        except anthropic.APIError as exc:
            return GateAborted(f"The judge call failed ({_api_error(exc)}); no verdict.")
        card = build_card(record)
        if parent_run_id is not None:
            card = card.model_copy(
                update={
                    "parent_run_id": parent_run_id,
                    "agent_version": spec.version,
                    "coach_note": coach_note,
                }
            )
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
        for agent in self.saved_agents():  # AC-81: saved brief agents beside the templates
            skills = ", ".join(k.name for k in agent.skills)
            cards.append(
                TemplateCard(agent.id, f"From brief: {agent.role[:60]}", skills, None, True)
            )
        return cards

    def agent_spec(self, agent_id: str) -> AgentSpec | None:
        """The spec whose id is `agent_id`: the latest coached version when a stored card holds
        one (agent_version > 1), else the template or the saved brief agent."""
        base = self._base_spec(agent_id)
        if base is None:
            return None
        return self._coached(agent_id) or base

    def _base_spec(self, agent_id: str) -> AgentSpec | None:
        for template_id in TEMPLATE_IDS:
            try:
                spec = load_template(template_id)
            except TemplateNotAvailable:
                continue
            if spec.id == agent_id:
                return spec
        return self._saved(agent_id)

    # --- saved brief agents (AC-81) ------------------------------------------------------

    def _saved(self, agent_id: str) -> AgentSpec | None:
        if self.agents_dir is None or not _BRIEF_ID.fullmatch(agent_id):
            return None
        path = self.agents_dir / f"{agent_id}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        checked = validate_agent_spec(raw) if isinstance(raw, dict) else None
        return checked if isinstance(checked, AgentSpec) else None

    def saved_agents(self) -> list[AgentSpec]:
        if self.agents_dir is None or not self.agents_dir.is_dir():
            return []
        found = [self._saved(p.stem) for p in sorted(self.agents_dir.glob("brief-*.json"))]
        return [a for a in found if a is not None]

    def save_brief_agent(self, spec: AgentSpec) -> AgentSpec:
        """Store a generated spec under a fresh `brief-` id. Raises `ValueError` when it cannot
        be saved; a server tool is refused (security finding S2)."""
        if self.agents_dir is None:
            raise ValueError("Saving agents is not configured.")
        if spec.source.kind != "brief":
            raise ValueError("Only a spec generated from a brief can be saved.")
        if any(not isinstance(t, ClientTool) for t in spec.tools):
            raise ValueError("A generated agent may not use server tools.")
        slug = re.sub(r"[^a-z0-9]+", "-", spec.id.lower()).strip("-")[:32] or "agent"
        agent_id = f"brief-{slug}-{secrets.token_hex(3)}"
        saved = spec.model_copy(update={"id": agent_id, "version": 1})
        checked = validate_agent_spec(saved.model_dump(mode="json"))
        if not isinstance(checked, AgentSpec):
            raise ValueError("The proposal does not validate.")
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        with (self.agents_dir / f"{agent_id}.json").open("x", encoding="utf-8") as f:
            f.write(checked.model_dump_json(indent=2))
        return checked

    async def run_gate_for_agent(self, agent_id: str) -> EvalCard | GateAborted:
        """AC-82: a full gate run on the current version of any known agent."""
        spec = self.agent_spec(agent_id)
        if spec is None:
            return GateAborted(f"Unknown agent: {agent_id}.")
        return await self._gate(spec)

    def _coached(self, agent_id: str) -> AgentSpec | None:
        card = self.latest_card(agent_id)
        if card is None or card.agent_version <= 1 or not card.agent_spec:
            return None
        checked = validate_agent_spec(card.agent_spec)
        return checked if isinstance(checked, AgentSpec) else None

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
            checked = preflight(spec.with_scenarios([scenario]).model_dump(mode="json"))
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


def _avatar_factory(env: Mapping[str, str], boson_key: str) -> AvatarFactory | None:
    """The avatar is optional: without all three LIVEKIT_* values the page has no avatar."""
    url = env.get("LIVEKIT_URL", "").strip()
    key = env.get("LIVEKIT_API_KEY", "").strip()
    secret = env.get("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and secret):
        return None
    from factory.live.avatar_livekit import LiveKitConfig, start_avatar  # lazy: demo works without

    config = LiveKitConfig(url, key, secret)
    return lambda: start_avatar(boson_key, config, AVATAR_MAX_DURATION_S)


def build_app(env: Mapping[str, str] | None, results_dir: Path) -> FactoryApp:
    """Fails with `ConfigError` before any network call when a key is missing."""
    env = os.environ if env is None else env
    boson_key = _required(env, "BOSON_API_KEY")
    anthropic_key = _required(env, "ANTHROPIC_API_KEY")
    judge_model = env.get("FACTORY_JUDGE_MODEL", "").strip() or DEFAULT_JUDGE_MODEL

    avatar = _avatar_factory(env, boson_key)
    http = httpx.AsyncClient(base_url=BOSON_API_BASE_URL, timeout=TTS_TIMEOUT_S)
    llm = anthropic.AsyncAnthropic(api_key=anthropic_key, max_retries=0)  # NFR: no retries
    return FactoryApp(
        sessions=lambda: BosonRealtimeSession(BOSON_REALTIME_URL, boson_key, time.monotonic),
        live_sessions=lambda: LiveBosonSession(BOSON_REALTIME_URL, boson_key, time.monotonic),
        avatar=avatar,
        audio=TurnAudioSource(
            BosonTts(http, boson_key), results_dir / "tts-cache", TEMPLATE_RECORDINGS_DIR
        ),
        judge=AnthropicJudge(llm, model_id=judge_model),
        store=FileCardStore(results_dir / "cards"),
        agents_dir=results_dir / "agents",
        brief_model=AnthropicBriefModel(llm, model_id=judge_model),
        coach_model=AnthropicCoachModel(llm, model_id=judge_model),
        _closers=(http.aclose, llm.close),
    )


class _LazyTts:
    """`TtsPort` that reads the key and opens the HTTP client on the first synthesis, so the
    film commands that never speak (timeline, run, render) run without BOSON_API_KEY."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env
        self._http: httpx.AsyncClient | None = None
        self._tts: BosonTts | None = None

    async def synthesise(self, text: str, voice: str) -> bytes:
        if self._tts is None:
            key = _required(self._env, "BOSON_API_KEY")  # ConfigError names the variable only
            self._http = httpx.AsyncClient(base_url=BOSON_API_BASE_URL, timeout=TTS_TIMEOUT_S)
            self._tts = BosonTts(self._http, key, TTS_MODEL)
        return await self._tts.synthesise(text, voice)

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()


def build_film(env: Mapping[str, str] | None, out_dir: Path) -> FilmApp:
    """The film recorder's services. Nothing is read or opened until a command needs it: the key
    on the first synthesis, Chromium on the first page, the HTTP client per `run`."""
    env = os.environ if env is None else env
    tts = _LazyTts(env)
    clients: list[httpx.AsyncClient] = []

    def server_factory(base_url: str) -> HttpServer:
        client = httpx.AsyncClient(base_url=base_url, timeout=10)
        clients.append(client)
        return HttpServer(client)

    async def close_clients() -> None:
        for client in clients:
            await client.aclose()

    return FilmApp(
        tts=tts,
        model=TTS_MODEL,
        page_factory=open_playwright_page,
        server_factory=server_factory,
        ffmpeg=Ffmpeg(),
        clock=lambda: datetime.now(UTC),
        closers=(tts.aclose, close_clients),
    )
