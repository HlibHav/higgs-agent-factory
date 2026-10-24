"""Plan step 27: the demo server (AC-37, AC-43, AC-44, AC-35, AC-26, AC-53, AC-32 page half).

Offline: starlette's TestClient drives the app; sessions are fakes, or the real session adapter
against the fake Realtime server running on its own event loop in a thread.
"""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from factory.__main__ import main
from factory.agent_spec.templates import TEMPLATE_IDS, load_template
from factory.composition import FactoryApp, LiveBosonSession, build_app
from factory.gate import runner
from factory.gate.card_builder import build_card
from factory.gate.card_store import FileCardStore
from factory.gate.records import GateRunRecord, Judgment, ScenarioRecord
from factory.gate.tts_cache import TurnAudioSource
from factory.live.session import LIVE_TTFA_LABEL, LiveAudioDelta
from factory.ports import (
    AudioDelta,
    ResponseDone,
    SessionEnded,
    SpeechStarted,
    SpeechStopped,
    TranscriptDelta,
)
from factory.web.app import _Inbox, _Outbox, create_web_app
from tests.doubles import (
    Delay,
    FakeBriefModel,
    FakeJudge,
    FakeSessionFactory,
    FakeTts,
    Refuse,
    make_spec,
)
from tests.fake_realtime_server import (
    audio_delta_event,
    close,
    fake_realtime_server,
    idle_timeout_event,
    send,
    speech_started_event,
    wait_for,
)

BOSON_KEY = "sk-test-BOSON-xyz"
ANTHROPIC_KEY = "sk-test-ANTH-xyz"
AGENT = "specialist-training"
GOOD = json.dumps({"label": "PASS", "rationale": "answered", "evidence": "Hello"})
PCM = b"\x07\x00" * 240


def _app(
    tmp_path: Path,
    *,
    sessions: Any = None,
    live: Any = None,
    judge: Any = None,
) -> FactoryApp:
    return FactoryApp(
        sessions=sessions or FakeSessionFactory(),
        audio=TurnAudioSource(FakeTts(), tmp_path / "tts", tmp_path / "rec"),
        judge=judge or FakeJudge([]),
        store=FileCardStore(tmp_path / "cards"),
        live_sessions=live,
    )


def _store_card(
    tmp_path: Path, agent_id: str, label: str, run_id: str = "20261024T120000Z-aa"
) -> Any:
    sc = ScenarioRecord(
        scenario_id="st-1",
        title="t",
        rubric=load_template(AGENT).scenarios[0].rubric,
        judgment=Judgment(label=label, rationale="why", evidence="quote"),  # type: ignore[arg-type]
        transcript="hello",
        tool_calls=[],
        expected_call_match=None,
        audio_source="synthesised",
    )
    record = GateRunRecord(
        agent_id=agent_id,
        run_id=run_id,
        ended_at=datetime(2026, 10, 24, 12, 0, tzinfo=UTC),
        scenarios=[sc],
        turns=[],
        usages=[],
        input_audio_s=10.0,
        output_audio_s=10.0,
        cause=None,
        cause_detail=None,
    )
    card = build_card(record)
    return card, FileCardStore(tmp_path / "cards").save(card)


def _client(app: FactoryApp, **kw: Any) -> TestClient:
    return TestClient(create_web_app(app, **kw))


def _receive_until_end(ws: WebSocketTestSession) -> list[dict[str, Any] | bytes]:
    """Every frame up to and including `ended`; the session scripts always end."""
    frames: list[dict[str, Any] | bytes] = []
    while True:
        message = ws.receive()
        if message["type"] == "websocket.close":
            return frames
        if message.get("bytes") is not None:
            frames.append(message["bytes"])
            continue
        payload = json.loads(message["text"])
        frames.append(payload)
        if payload["type"] == "ended":
            return frames


def _texts(frames: list[dict[str, Any] | bytes]) -> list[dict[str, Any]]:
    return [f for f in frames if isinstance(f, dict)]


@contextmanager
def _fake_boson(script: list[Any]) -> Iterator[str]:
    """The fake Realtime server on its own loop in a thread (TestClient owns its own loop)."""
    started = threading.Event()
    stop = threading.Event()
    box: dict[str, str] = {}

    def run() -> None:
        async def main_() -> None:
            async with fake_realtime_server(script) as (url, _):
                box["url"] = url
                started.set()
                while not stop.is_set():
                    await asyncio.sleep(0.02)

        asyncio.run(main_())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert started.wait(10)
    try:
        yield box["url"]
    finally:
        stop.set()
        thread.join(10)


# --- plain routes --------------------------------------------------------------------------


def test_templates_lists_every_registry_template(tmp_path: Path) -> None:
    body = _client(_app(tmp_path)).get("/api/templates").json()
    assert [c["template_id"] for c in body] == list(TEMPLATE_IDS)  # five (AC-38)
    assert len(body) == 5
    for card in body:
        assert {"template_id", "name", "description", "source_url"} <= set(card)
    assert next(c for c in body if c["template_id"] == AGENT)["name"] == "Specialist Training"


def test_spec_route_returns_the_agent_spec(tmp_path: Path) -> None:
    client = _client(_app(tmp_path))
    body = client.get(f"/api/agents/{AGENT}/spec").json()
    assert body == load_template(AGENT).model_dump(mode="json")  # AC-49
    assert client.get("/api/agents/nope/spec").status_code == 404


def _skill(sid: str) -> dict[str, Any]:
    return {
        "id": sid,
        "name": sid.title(),
        "purpose": f"does {sid}",
        "procedure": f"step for {sid}",
        "tools": [],
        "scenarios": [
            {
                "id": f"{sid}-1",
                "title": f"{sid} scenario",
                "user_voice": "chloe",
                "user_turns": [{"text": "Hello there."}],
                "expected_tool_call": None,
                "rubric": {
                    "pass_criteria": ["ok"],
                    "partial_criteria": ["meh"],
                    "fail_criteria": ["bad"],
                },
            }
        ],
    }


def _two_skill_reply() -> str:
    spec = make_spec()
    spec.update(
        schema_version=2,
        persona="Be brief.",
        skills=[_skill("greet"), _skill("quote")],
    )
    for old in ("instructions", "tools", "scenarios"):
        spec.pop(old, None)
    return json.dumps(spec)


def test_spec_route_carries_persona_and_skills(tmp_path: Path) -> None:
    body = _client(_app(tmp_path)).get(f"/api/agents/{AGENT}/spec").json()
    assert body["persona"] and body["skills"]
    assert {"id", "name", "purpose", "procedure", "tools", "scenarios"} <= set(body["skills"][0])


def test_card_route_carries_skills_and_judge_agreement(tmp_path: Path) -> None:
    _store_card(tmp_path, AGENT, "PASS")
    card = _client(_app(tmp_path)).get(f"/api/agents/{AGENT}/card/latest").json()["card"]
    assert card["skills"] and {"skill_id", "name", "scenarios_run", "passed"} <= set(
        card["skills"][0]
    )
    assert "judge_agreement_rate" in card and "agent_version" in card
    assert "agent_spec" not in card


def test_coach_route_404_without_pair_and_200_with_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _app(tmp_path)
    client = _client(app)
    assert client.get(f"/api/agents/{AGENT}/coach").status_code == 404
    before, _ = _store_card(tmp_path, AGENT, "FAIL", run_id="20261024T120000Z-aa")
    after, _ = _store_card(tmp_path, AGENT, "PASS", run_id="20261024T130000Z-bb")
    monkeypatch.setattr(app, "coach_pair", lambda agent_id: (before, after), raising=False)
    body = client.get(f"/api/agents/{AGENT}/coach").json()
    assert body["before"]["verdict"] == "rejected" and body["after"]["verdict"] == "released"
    assert body["diff"]["verdict"] == {"key": "verdict", "before": "rejected", "after": "released"}
    assert body["diff"]["before_run_id"] == before.run_id
    assert "agent_spec" not in body["after"]


def test_brief_route_proposes_two_skills_without_a_gate_run(tmp_path: Path) -> None:
    app = _app(tmp_path)
    model = FakeBriefModel(_two_skill_reply())
    app.brief_model = model
    client = _client(app)
    response = client.post("/api/brief", json={"brief": "a shop trainer"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [k["id"] for k in body["skills"]] == ["greet", "quote"] and body["persona"]
    assert model.calls == 1
    assert list((tmp_path / "cards").glob("*/*")) == []  # AC-79: proposed, not gated


def test_brief_route_errors(tmp_path: Path) -> None:
    app = _app(tmp_path)
    client = _client(app)
    assert client.post("/api/brief", json={"brief": "hi"}).status_code == 503  # no model
    model = FakeBriefModel("not json")
    app.brief_model = model
    long = client.post("/api/brief", json={"brief": "x" * 1001})
    assert long.status_code == 400 and "1,000" in long.json()["detail"] and model.calls == 0
    issues = client.post("/api/brief", json={"brief": "hi"})
    assert issues.status_code == 422 and issues.json()["issues"][0]["field"] == "model_reply"
    assert client.post("/api/brief", json={}).status_code == 400


def test_scenarios_route(tmp_path: Path) -> None:
    body = _client(_app(tmp_path)).get(f"/api/agents/{AGENT}/scenarios").json()
    assert body and set(body[0]) == {"scenario_id", "title"}


def test_page_served_from_static_file_or_404(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    page.write_text("<h1>demo</h1>", encoding="utf-8")
    ok = _client(_app(tmp_path), index_path=page).get("/")
    assert ok.status_code == 200 and ok.text == "<h1>demo</h1>"
    assert ok.headers["content-type"].startswith("text/html")
    assert ok.headers["x-content-type-options"] == "nosniff"
    missing = _client(_app(tmp_path), index_path=tmp_path / "none.html").get("/")
    assert missing.status_code == 404


def test_ac52_latest_card_with_text_or_404(tmp_path: Path) -> None:
    client = _client(_app(tmp_path))
    gone = client.get(f"/api/agents/{AGENT}/card/latest")
    assert gone.status_code == 404 and gone.json() == {"detail": "no gate run yet"}
    card, _ = _store_card(tmp_path, AGENT, "FAIL")
    body = client.get(f"/api/agents/{AGENT}/card/latest").json()
    assert body["card"]["run_id"] == card.run_id and body["card"]["verdict"] == "rejected"
    assert body["card"]["ended_at"].startswith("2026-10-24T12:00:00")
    assert "Verdict: rejected" in body["text"]


def test_ac32_page_card_text_has_no_amount_labelled_billed(tmp_path: Path) -> None:
    _store_card(tmp_path, AGENT, "PASS")
    text = _client(_app(tmp_path)).get(f"/api/agents/{AGENT}/card/latest").json()["text"].lower()
    assert "estimated audio cost: $" in text
    for line in text.splitlines():  # the AC-31 text names "billed" but carries no amount
        if any(word in line for word in ("billed", "actual", "invoiced")):
            assert "$" not in line


def test_unsafe_agent_id_is_a_404_not_a_path(tmp_path: Path) -> None:
    client = _client(_app(tmp_path))
    assert client.get("/api/agents/..%2Fx/card/latest").status_code == 404


def test_cross_site_post_and_websocket_are_refused(tmp_path: Path) -> None:
    client = _client(_app(tmp_path))
    evil = {"Origin": "http://evil.example"}
    post = client.post(f"/api/agents/{AGENT}/scenarios/st-1/check", headers=evil)
    assert post.status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/live/{AGENT}", headers=evil):
            pass
    same = {"Origin": "http://testserver"}
    assert client.get("/api/templates", headers=evil).status_code == 200  # reads stay open
    assert client.post("/api/agents/nope/scenarios/x/check", headers=same).status_code == 404


# --- AC-53: single-scenario check ----------------------------------------------------------


def _check_script() -> list[Any]:
    return [
        AudioDelta("r1", 4800, 1000.4),
        TranscriptDelta("r1", "Hello, welcome.", 1000.4),
        ResponseDone("r1", "completed", None, 1000.5),
    ]


def test_ac53_single_check_marked_and_stored_card_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "QUIET_WINDOW_S", 0.05)
    card, path = _store_card(tmp_path, AGENT, "FAIL")
    before = path.read_bytes()
    judge = FakeJudge([GOOD, GOOD])
    sessions = FakeSessionFactory(_check_script(), restamp=True)
    client = _client(_app(tmp_path, sessions=sessions, judge=judge))
    scenario_id = load_template(AGENT).scenarios[0].id

    response = client.post(f"/api/agents/{AGENT}/scenarios/{scenario_id}/check")
    body = response.json()
    assert response.status_code == 200, body
    assert body["marker"] == "single-scenario check"
    assert (body["label"], body["rationale"], body["evidence"]) == ("PASS", "answered", "Hello")
    assert body["scenario_id"] == scenario_id and body["stored_verdict"] == "rejected"
    assert body["ttfa_ms"] is not None
    assert sessions.calls == 1 and len(judge.requests) == 2  # this scenario, k = 2 (AC-75)
    assert path.read_bytes() == before  # file untouched
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]  # and nothing new
    latest = client.get(f"/api/agents/{AGENT}/card/latest").json()["card"]
    assert latest["verdict"] == "rejected" and latest["run_id"] == card.run_id


def test_single_check_failure_is_a_502_with_plain_text(tmp_path: Path) -> None:
    sessions = FakeSessionFactory([Refuse("voice <b>not</b> found")])
    client = _client(_app(tmp_path, sessions=sessions))
    scenario_id = load_template(AGENT).scenarios[0].id
    response = client.post(f"/api/agents/{AGENT}/scenarios/{scenario_id}/check")
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "voice <b>not</b> found"}  # data, not markup
    assert list((tmp_path / "cards").glob("*/*")) == []  # nothing stored


# --- live WebSocket ------------------------------------------------------------------------


def _live_app(
    tmp_path: Path, script: list[Any], **kw: Any
) -> tuple[FactoryApp, FakeSessionFactory]:
    live = FakeSessionFactory(script)
    return _app(tmp_path, live=live, **kw), live


def test_live_ready_forwarding_barge_in_ttfa_transcript(tmp_path: Path) -> None:
    _store_card(tmp_path, AGENT, "FAIL")
    script: list[Any] = [
        SpeechStopped(10.0),
        LiveAudioDelta("r1", len(PCM), 10.3, pcm=PCM),
        TranscriptDelta("r1", "Hi there.", 10.3),
        ResponseDone("r1", "completed", None, 10.4),
        Delay(0.4),  # let the mic frame arrive first
        SpeechStarted(11.0),
        SessionEnded("closed", None, None, 12.0),
    ]
    app, live = _live_app(tmp_path, script)
    with _client(app).websocket_connect(f"/ws/live/{AGENT}") as ws:
        ws.send_bytes(b"\x01\x00" * 480)
        frames = _receive_until_end(ws)
    texts = _texts(frames)
    ready = texts[0]
    assert ready["type"] == "ready" and ready["agent_id"] == AGENT
    assert ready["released"] is False and ready["verdict"] == "rejected"  # AC-36
    assert ready["run_id"] == "20261024T120000Z-aa" and ready["limit_s"] == 180
    assert PCM in frames  # AudioDelta -> binary out
    ttfa = next(t for t in texts if t["type"] == "ttfa")
    assert abs(ttfa["ms"] - 300.0) < 1.0 and ttfa["label"] == LIVE_TTFA_LABEL  # AC-26
    assert {"type": "transcript", "role": "assistant", "text": "Hi there."} in texts
    assert {"type": "speech_started"} in texts  # F15 barge-in
    assert texts[-1]["type"] == "ended" and texts[-1]["reason"] == "closed"
    session = live.sessions[0]
    assert [s.pcm for s in session.sends if s.kind == "audio"] == [b"\x01\x00" * 480]
    assert session.closed


def test_live_ready_for_a_released_agent_and_for_none(tmp_path: Path) -> None:
    script: list[Any] = [SessionEnded("closed", None, None, 1.0)]
    app, _ = _live_app(tmp_path, script)
    with _client(app).websocket_connect(f"/ws/live/{AGENT}") as ws:
        ready = _receive_until_end(ws)[0]
    assert isinstance(ready, dict)
    assert (ready["released"], ready["verdict"], ready["run_id"]) == (False, None, None)
    _store_card(tmp_path, AGENT, "PASS")
    app, _ = _live_app(tmp_path, script)
    with _client(app).websocket_connect(f"/ws/live/{AGENT}") as ws:
        ready = _receive_until_end(ws)[0]
    assert isinstance(ready, dict) and ready["released"] is True and ready["verdict"] == "released"


def test_live_unknown_agent_is_an_ended_error(tmp_path: Path) -> None:
    app, live = _live_app(tmp_path, [])
    with _client(app).websocket_connect("/ws/live/nope") as ws:
        (end,) = _receive_until_end(ws)
    assert isinstance(end, dict) and end["reason"] == "error" and live.calls == 0


def test_live_stop_message_ends_and_closes_the_session(tmp_path: Path) -> None:
    app, live = _live_app(tmp_path, [Delay(30)])
    with _client(app).websocket_connect(f"/ws/live/{AGENT}") as ws:
        ws.send_bytes(b"\x01\x00" * 100)
        ws.send_text(json.dumps({"type": "stop"}))
        texts = _texts(_receive_until_end(ws))
    assert texts[-1]["reason"] == "closed"
    assert live.sessions[0].closed


def test_live_client_leaving_closes_the_upstream_session(tmp_path: Path) -> None:
    app, live = _live_app(tmp_path, [Delay(30)])
    client = _client(app)
    with client.websocket_connect(f"/ws/live/{AGENT}") as ws:
        ws.receive_text()  # ready
    deadline = time.monotonic() + 10
    while not live.sessions[0].closed and time.monotonic() < deadline:
        time.sleep(0.02)
    assert live.sessions[0].closed
    # and the slot is free again
    app2_script: list[Any] = [SessionEnded("closed", None, None, 1.0)]
    live.script = app2_script
    with client.websocket_connect(f"/ws/live/{AGENT}") as ws:
        assert _texts(_receive_until_end(ws))[-1]["reason"] == "closed"


def test_live_second_session_is_refused_while_one_runs(tmp_path: Path) -> None:
    app, live = _live_app(tmp_path, [Delay(30)])
    client = _client(app)
    with client.websocket_connect(f"/ws/live/{AGENT}") as first:
        first.receive_text()
        with client.websocket_connect(f"/ws/live/{AGENT}") as second:
            (end,) = _receive_until_end(second)
        assert isinstance(end, dict) and end["reason"] == "error"
        assert "Another live session" in end["message"]
    assert live.calls == 1


def test_ac35_limit_reached_over_the_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, live = _live_app(tmp_path, [Delay(30)])
    short = load_template(AGENT).model_copy(
        update={
            "budget": load_template(AGENT).budget.model_copy(update={"max_live_session_s": 0.5})
        }
    )
    monkeypatch.setattr(app, "agent_spec", lambda agent_id: short)
    started = time.monotonic()
    with _client(app).websocket_connect(f"/ws/live/{AGENT}") as ws:
        frames = _texts(_receive_until_end(ws))
    assert frames[0]["limit_s"] == 0  # int(0.5): the page shows whole seconds
    assert frames[-1]["reason"] == "limit reached" and "limit" in frames[-1]["message"]
    assert 0.45 <= time.monotonic() - started < 5
    assert live.sessions[0].closed


def test_error_text_escaped(tmp_path: Path) -> None:
    hostile = '<script>alert("x")</script> "quoted" \\ \n'
    app, _ = _live_app(tmp_path, [Refuse(hostile)])
    with _client(app).websocket_connect(f"/ws/live/{AGENT}") as ws:
        message = ws.receive()
        payload = json.loads(message["text"])  # plain JSON, escapes intact
    assert payload["type"] == "ended" and hostile[:30] in payload["message"]
    assert "\n" not in message["text"]  # the raw newline travelled as \n


def test_ac37_no_key_in_any_response_or_message(tmp_path: Path) -> None:
    env = {"BOSON_API_KEY": BOSON_KEY, "ANTHROPIC_API_KEY": ANTHROPIC_KEY}
    built = build_app(env, tmp_path / "results")
    page = tmp_path / "index.html"
    page.write_text("<h1>demo</h1>", encoding="utf-8")
    _store_card(tmp_path / "results", AGENT, "FAIL")
    script: list[Any] = [
        LiveAudioDelta("r1", len(PCM), 1.0, pcm=PCM),
        SessionEnded("quota refused", 4429, None, 2.0),
    ]
    built.live_sessions = FakeSessionFactory(script)
    built.sessions = FakeSessionFactory(_check_script(), restamp=True)
    built.judge = FakeJudge([GOOD, GOOD])
    client = _client(built, index_path=page)
    bodies = [client.get("/").text]
    paths = [
        "/api/templates",
        f"/api/agents/{AGENT}/spec",
        f"/api/agents/{AGENT}/card/latest",
        f"/api/agents/{AGENT}/scenarios",
        "/api/agents/nope/spec",
        f"/api/agents/{AGENT}/coach",
        "/openapi.json",
    ]
    bodies += [client.get(p).text for p in paths]
    built.brief_model = FakeBriefModel(_two_skill_reply())
    bodies.append(client.post("/api/brief", json={"brief": "a trainer"}).text)
    bodies.append(client.post("/api/brief", json={"brief": "x" * 1001}).text)
    bodies.append(client.post(f"/api/agents/{AGENT}/scenarios/nope/check").text)
    with client.websocket_connect(f"/ws/live/{AGENT}") as ws:
        for frame in _receive_until_end(ws):
            bodies.append(frame.hex() if isinstance(frame, bytes) else json.dumps(frame))
    assert len(bodies) > 8
    for body in bodies:
        assert BOSON_KEY not in body and ANTHROPIC_KEY not in body
    for headers in (client.get("/api/templates").headers, client.get("/").headers):
        assert BOSON_KEY not in str(dict(headers)) and ANTHROPIC_KEY not in str(dict(headers))


# --- AC-43 / AC-44 through the real adapter and the fake Realtime server --------------------


def _wire_app(tmp_path: Path, url: str) -> FactoryApp:
    return _app(tmp_path, live=lambda: LiveBosonSession(url=url, api_key=BOSON_KEY))


def test_ac43_idle_timeout_says_inactivity(tmp_path: Path) -> None:
    script = [
        wait_for("session.update"),
        send(audio_delta_event("r1", 960)),
        send(idle_timeout_event()),
    ]
    with _fake_boson(script) as url:
        with _client(_wire_app(tmp_path, url)).websocket_connect(f"/ws/live/{AGENT}") as ws:
            frames = _receive_until_end(ws)
    texts = _texts(frames)
    assert texts[-1]["reason"] == "inactivity" and "inactivity" in texts[-1]["message"]
    assert any(isinstance(f, bytes) and len(f) == 960 for f in frames)  # wire PCM reached us


def test_ac44_quota_close_says_refused_and_does_not_reconnect(tmp_path: Path) -> None:
    quota = {"type": "error", "error": {"type": "insufficient_quota", "message": "refused"}}
    with _fake_boson([wait_for("session.update"), send(quota), close(4429)]) as url:
        client = _client(_wire_app(tmp_path, url))
        with client.websocket_connect(f"/ws/live/{AGENT}") as ws:
            texts = _texts(_receive_until_end(ws))
    assert texts[-1]["reason"] == "quota refused"
    assert "quota" in texts[-1]["message"]


def test_ac44_close_before_session_created_is_also_quota_refused(tmp_path: Path) -> None:
    with _fake_boson([close(4429)]) as url:
        with _client(_wire_app(tmp_path, url)).websocket_connect(f"/ws/live/{AGENT}") as ws:
            texts = _texts(_receive_until_end(ws))
    assert texts[-1]["reason"] == "quota refused"


def test_wire_speech_started_reaches_the_page(tmp_path: Path) -> None:
    script = [
        wait_for("session.update"),
        send(audio_delta_event("r1", 960)),
        send(speech_started_event()),
        send(idle_timeout_event()),
    ]
    with _fake_boson(script) as url:
        with _client(_wire_app(tmp_path, url)).websocket_connect(f"/ws/live/{AGENT}") as ws:
            texts = _texts(_receive_until_end(ws))
    assert {"type": "speech_started"} in texts


# --- CLI -----------------------------------------------------------------------------------


def test_serve_subcommand_binds_loopback_and_pins_the_ws_library(tmp_path: Path) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    def runner_(app: Any, **kw: Any) -> None:
        calls.append((app, kw))

    env = {"BOSON_API_KEY": BOSON_KEY, "ANTHROPIC_API_KEY": ANTHROPIC_KEY}
    code = main(
        ["serve", "--port", "8123"],
        env=env,
        results_dir=tmp_path,
        server_runner=runner_,
    )
    assert code == 0
    ((app, kw),) = calls
    assert kw == {"host": "127.0.0.1", "port": 8123, "ws": "websockets"}
    assert app.title == "Higgs Agent Factory"


def test_serve_defaults_to_port_8000(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}
    env = {"BOSON_API_KEY": BOSON_KEY, "ANTHROPIC_API_KEY": ANTHROPIC_KEY}
    main(["serve"], env=env, results_dir=tmp_path, server_runner=lambda app, **kw: seen.update(kw))
    assert seen["port"] == 8000 and seen["host"] == "127.0.0.1"


# --- bounded queues ------------------------------------------------------------------------


def test_outbox_drops_oldest_audio_keeps_text_and_clears_on_barge_in() -> None:
    async def main_() -> None:
        box = _Outbox(max_audio=3)
        box.put_text("first")
        for i in range(5):
            box.put_audio(bytes([i]))
        box.put_text("last")
        got = []
        box.close()
        while (item := await box.get()) is not None:
            got.append(item)
        assert got == ["first", b"\x02", b"\x03", b"\x04", "last"]  # oldest two audio dropped
        box = _Outbox()
        box.put_audio(b"a")
        box.put_text("keep")
        box.clear_audio()
        box.close()
        assert [await box.get(), await box.get()] == ["keep", None]
        box.kill()
        box.put_audio(b"x")  # a dead box accepts nothing
        assert await box.get() is None

    asyncio.run(main_())


def test_inbox_is_bounded_and_end_always_lands() -> None:
    async def main_() -> None:
        inbox = _Inbox()
        for _ in range(500):
            inbox.push(b"\x00\x00")  # beyond the bound the frame is dropped, not queued
        inbox.end()
        count = 0
        async for _frame in inbox.frames():
            count += 1
        assert 0 < count <= 100

    asyncio.run(main_())
