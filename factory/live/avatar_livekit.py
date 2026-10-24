"""LiveKit adapter for the Higgs avatar (F11): the only module that imports livekit.

`start_avatar` mints the avatar's and our publisher's tokens, joins the room as the publisher,
creates the avatar session (`POST /v1/avatar/sessions`, F11), and returns an `AvatarPort`.
Assistant PCM goes to the avatar over a LiveKit data stream (`DataStreamAudioOutput`, ADR
2026-10-24-livekit-agents-for-avatar). The browser gets a subscribe-only token that expires in
`VIEWER_TTL_S`; the LiveKit secret and the Boson key never leave this module.
"""

import logging
import uuid
from datetime import timedelta

import httpx
from livekit import api, rtc
from livekit.agents.voice.avatar import DataStreamAudioOutput

from factory.ports import AvatarError, AvatarInfo, AvatarPort

log = logging.getLogger("factory.avatar")

AVATAR_SESSIONS_URL = "https://api.boson.ai/v1/avatar/sessions"  # F11
AVATAR_ID = "builtin_claire_v1"
AVATAR_IDENTITY = "boson-avatar"
PUBLISHER_IDENTITY = "agent"
SAMPLE_RATE = 24000  # F11: 24 kHz 16-bit mono PCM
OUTPUT_SIZE = {"width": 480, "height": 640}
VIEWER_TTL_S = 600  # at most 10 minutes
HTTP_TIMEOUT_S = 30.0


class LiveKitConfig:
    def __init__(self, url: str, api_key: str, api_secret: str) -> None:
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret

    def token(self, identity: str, grants: api.VideoGrants, ttl_s: int) -> str:
        return (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(identity)
            .with_grants(grants)
            .with_ttl(timedelta(seconds=ttl_s))
            .to_jwt()
        )


class LiveKitAvatar:
    def __init__(
        self,
        info: AvatarInfo,
        room: rtc.Room,
        output: DataStreamAudioOutput,
        http: httpx.AsyncClient,
        session_id: str,
        headers: dict[str, str],
    ) -> None:
        self._info = info
        self._room = room
        self._output = output
        self._http = http
        self._session_id = session_id
        self._headers = headers
        self._closed = False

    @property
    def info(self) -> AvatarInfo:
        return self._info

    async def audio(self, pcm: bytes) -> None:
        if self._closed:
            raise AvatarError("The avatar is closed.")
        try:
            frame = rtc.AudioFrame(pcm, SAMPLE_RATE, 1, len(pcm) // 2)
            await self._output.capture_frame(frame)
        except Exception as exc:  # noqa: BLE001 - any livekit failure means the avatar is down
            raise AvatarError(f"The avatar stopped ({type(exc).__name__}).") from None

    async def clear(self) -> None:
        if not self._closed:
            self._output.clear_buffer()

    async def flush(self) -> None:
        if not self._closed:
            self._output.flush()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._http.delete(
                f"{AVATAR_SESSIONS_URL}/{self._session_id}", headers=self._headers
            )
        except Exception as exc:  # noqa: BLE001 - the session also ends at expires_at (F11)
            log.warning("avatar session delete failed (%s)", type(exc).__name__)
        try:
            await self._room.disconnect()
        except Exception as exc:  # noqa: BLE001
            log.warning("avatar room disconnect failed (%s)", type(exc).__name__)
        await self._http.aclose()


async def start_avatar(
    boson_key: str, lk: LiveKitConfig, max_duration_s: int, avatar_id: str = AVATAR_ID
) -> AvatarPort:
    """Create the room session; raises `AvatarError` with a safe message on any failure."""
    room_name = f"avatar-{uuid.uuid4().hex[:12]}"
    ttl = max_duration_s + 300  # F11: the avatar token must outlast the session
    avatar_token = lk.token(
        AVATAR_IDENTITY,
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_publish_data=True,
            can_publish_sources=["camera", "microphone"],
        ),
        ttl,
    )
    publisher_token = lk.token(
        PUBLISHER_IDENTITY,
        api.VideoGrants(room_join=True, room=room_name, can_publish_data=True, can_subscribe=True),
        ttl,
    )
    viewer_identity = f"viewer-{uuid.uuid4().hex[:8]}"
    viewer_token = lk.token(
        viewer_identity,
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_subscribe=True,
            can_publish=False,
            can_publish_data=False,
        ),
        VIEWER_TTL_S,
    )
    room = rtc.Room()
    http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)
    headers = {"Authorization": f"Bearer {boson_key}"}
    session_id: str | None = None
    try:
        await room.connect(lk.url, publisher_token)
        body = {
            "avatar_id": avatar_id,
            "output": OUTPUT_SIZE,
            "max_duration_seconds": max_duration_s,
            "transport": {
                "type": "livekit",
                "url": lk.url,
                "room_name": room_name,
                "participant_token": avatar_token,
                "participant_identity": AVATAR_IDENTITY,
                "publisher_identity": PUBLISHER_IDENTITY,
                "audio_source": "data_stream",
            },
        }
        response = await http.post(AVATAR_SESSIONS_URL, json=body, headers=headers)
        if response.status_code != 201:
            raise AvatarError(_refusal(response))
        session_id = str(response.json()["id"])
        output = DataStreamAudioOutput(
            room,
            destination_identity=AVATAR_IDENTITY,
            sample_rate=SAMPLE_RATE,
            wait_remote_track=rtc.TrackKind.KIND_AUDIO,
        )
        info = AvatarInfo(lk.url, room_name, viewer_token, AVATAR_IDENTITY)
        return LiveKitAvatar(info, room, output, http, session_id, headers)
    except AvatarError:
        await _abandon(room, http, session_id, headers)
        raise
    except Exception as exc:  # noqa: BLE001 - never leak the exception text (it may hold a URL)
        await _abandon(room, http, session_id, headers)
        raise AvatarError(f"The avatar could not start ({type(exc).__name__}).") from None


def _refusal(response: httpx.Response) -> str:
    code = ""
    try:
        err = response.json().get("error")
        code = err.get("code", "") if isinstance(err, dict) else ""
    except ValueError:
        pass
    suffix = f", {code[:60]}" if code else ""
    return f"The avatar was refused (status {response.status_code}{suffix})."  # F11 (429 capacity)


async def _abandon(
    room: rtc.Room, http: httpx.AsyncClient, session_id: str | None, headers: dict[str, str]
) -> None:
    if session_id:
        try:
            await http.delete(f"{AVATAR_SESSIONS_URL}/{session_id}", headers=headers)
        except Exception:  # noqa: BLE001
            pass
    try:
        await room.disconnect()
    except Exception:  # noqa: BLE001
        pass
    await http.aclose()
