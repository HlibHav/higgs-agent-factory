"""Optional avatar (ADR 2026-10-24-livekit-agents-for-avatar, F11): endpoint and live wiring,
all offline with doubles. The avatar must never break audio-only live talk."""

from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from factory.live.session import LiveAudioDelta
from factory.ports import AvatarError, ResponseDone, SessionEnded, SpeechStarted, TranscriptDelta
from tests.doubles import Delay, FakeAvatarFactory, FakeSessionFactory
from tests.test_web import AGENT, PCM, _app, _client, _receive_until_end, _texts

SCRIPT: list[Any] = [
    LiveAudioDelta("r1", len(PCM), 1.0, pcm=PCM),
    TranscriptDelta("r1", "Hi.", 1.0),
    ResponseDone("r1", "completed", None, 1.1),
    Delay(0.3),
    SpeechStarted(2.0),
    SessionEnded("closed", None, None, 3.0),
]


def _avatar_client(tmp_path: Path, factory: Any) -> TestClient:
    app = _app(tmp_path, live=FakeSessionFactory(SCRIPT))
    app.avatar = factory
    return _client(app)


def test_endpoint_returns_only_url_room_token_identity(tmp_path: Path) -> None:
    client = _avatar_client(tmp_path, FakeAvatarFactory())
    body = client.post("/api/avatar/session").json()
    assert set(body) == {"url", "room", "viewer_token", "avatar_identity"}
    assert body["room"] == "room-1" and body["viewer_token"] == "viewer-tok"


def test_endpoint_503_when_not_configured_and_502_on_failure(tmp_path: Path) -> None:
    assert _avatar_client(tmp_path, None).post("/api/avatar/session").status_code == 503
    failing = FakeAvatarFactory(error=AvatarError("The avatar was refused (status 429)."))
    reply = _avatar_client(tmp_path, failing).post("/api/avatar/session")
    assert reply.status_code == 502 and "429" in reply.text


def test_live_with_avatar_sends_pcm_to_avatar_not_to_page_and_closes_it(tmp_path: Path) -> None:
    factory = FakeAvatarFactory()
    client = _avatar_client(tmp_path, factory)
    room = client.post("/api/avatar/session").json()["room"]
    with client.websocket_connect(f"/ws/live/{AGENT}?avatar={room}") as ws:
        frames = _receive_until_end(ws)
    avatar = factory.created[0]
    assert avatar.audio_in == [PCM] and PCM not in frames  # no double audio
    assert avatar.flushes == 1 and avatar.clears == 1  # response end, barge-in
    assert avatar.closed == 1  # session deleted when live talk ends


def test_avatar_failure_falls_back_to_page_audio(tmp_path: Path) -> None:
    factory = FakeAvatarFactory(fail_audio=True)
    client = _avatar_client(tmp_path, factory)
    room = client.post("/api/avatar/session").json()["room"]
    with client.websocket_connect(f"/ws/live/{AGENT}?avatar={room}") as ws:
        frames = _receive_until_end(ws)
    assert PCM in frames and {"type": "avatar_off"} in _texts(frames)
    assert factory.created[0].closed == 1


def test_live_without_avatar_param_is_unchanged_and_releases_a_stale_avatar(
    tmp_path: Path,
) -> None:
    factory = FakeAvatarFactory()
    client = _avatar_client(tmp_path, factory)
    client.post("/api/avatar/session")
    with client.websocket_connect(f"/ws/live/{AGENT}") as ws:
        frames = _receive_until_end(ws)
    assert PCM in frames
    assert factory.created[0].audio_in == [] and factory.created[0].closed == 1


def test_delete_releases_a_pending_avatar(tmp_path: Path) -> None:
    factory = FakeAvatarFactory()
    client = _avatar_client(tmp_path, factory)
    client.post("/api/avatar/session")
    assert client.delete("/api/avatar/session").status_code == 200
    assert factory.created[0].closed == 1


def test_create_waits_out_capacity_exhausted_then_succeeds(monkeypatch: Any) -> None:
    import asyncio as _asyncio

    import httpx

    from factory.live import avatar_livekit as av

    replies = [
        httpx.Response(
            429, headers={"retry-after": "5"}, json={"error": {"code": "capacity_exhausted"}}
        ),
        httpx.Response(201, json={"id": "avrt_1"}),
    ]
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(av.asyncio, "sleep", fake_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: replies.pop(0)))
    response = _asyncio.run(av._create(client, {}, {}))
    assert response.status_code == 201 and slept == [5.0]


def test_create_does_not_retry_quota_and_names_capacity(monkeypatch: Any) -> None:
    import asyncio as _asyncio

    import httpx

    from factory.live import avatar_livekit as av

    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={"error": {"code": "insufficient_quota"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = _asyncio.run(av._create(client, {}, {}))
    assert response.status_code == 429 and calls == [1]
    busy = httpx.Response(429, json={"error": {"code": "capacity_exhausted"}})
    assert "slot is busy" in av._refusal(busy)
