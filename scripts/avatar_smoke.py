"""Live smoke for the Higgs avatar (F11, F12): spends cents (about 10 s of avatar at $0.07/min).

Creates a LiveKit room session via POST /v1/avatar/sessions, joins as the publisher, pushes
~2 s of 24 kHz PCM through DataStreamAudioOutput, waits for the avatar's video track, then
DELETEs the session. Needs BOSON_API_KEY, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in
the environment. Never prints a key or token.
Run: `set -a; source .env; set +a; uv run python scripts/avatar_smoke.py`.
"""

import asyncio
import math
import os
import struct
import sys
import uuid
from datetime import timedelta

import httpx
from livekit import api, rtc
from livekit.agents.voice.avatar import DataStreamAudioOutput

BOSON_URL = "https://api.boson.ai/v1/avatar/sessions"
AVATAR_ID = "builtin_claire_v1"
AVATAR_IDENTITY = "boson-avatar"
PUBLISHER_IDENTITY = "agent"
SAMPLE_RATE = 24000
VIDEO_WAIT_S = 30.0


def _token(identity: str, grants: api.VideoGrants) -> str:
    return (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_grants(grants)
        .with_ttl(timedelta(minutes=10))
        .to_jwt()
    )


def _sine(seconds: float) -> bytes:
    n = int(SAMPLE_RATE * seconds)
    return b"".join(
        struct.pack("<h", int(6000 * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)))
        for i in range(n)
    )


async def main() -> int:
    url, room_name = os.environ["LIVEKIT_URL"], f"smoke-{uuid.uuid4().hex[:8]}"
    avatar_token = _token(
        AVATAR_IDENTITY,
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_publish_data=True,
            can_publish_sources=["camera", "microphone"],
        ),
    )
    pub_token = _token(
        PUBLISHER_IDENTITY,
        api.VideoGrants(room_join=True, room=room_name, can_publish_data=True, can_subscribe=True),
    )
    room = rtc.Room()
    video_seen = asyncio.Event()

    @room.on("track_subscribed")
    def _on_track(track: rtc.Track, _pub: rtc.RemoteTrackPublication, p: rtc.RemoteParticipant):
        print(f"track_subscribed kind={track.kind} from={p.identity}")
        if track.kind == rtc.TrackKind.KIND_VIDEO and p.identity == AVATAR_IDENTITY:
            video_seen.set()

    await room.connect(url, pub_token)
    session_id = None
    video = False
    async with httpx.AsyncClient(timeout=30) as http:
        headers = {"Authorization": f"Bearer {os.environ['BOSON_API_KEY']}"}
        try:
            body = {
                "avatar_id": AVATAR_ID,
                "output": {"width": 480, "height": 640},
                "max_duration_seconds": 120,
                "transport": {
                    "type": "livekit",
                    "url": url,
                    "room_name": room_name,
                    "participant_token": avatar_token,
                    "participant_identity": AVATAR_IDENTITY,
                    "publisher_identity": PUBLISHER_IDENTITY,
                    "audio_source": "data_stream",
                },
            }
            r = await http.post(BOSON_URL, json=body, headers=headers)
            print(f"POST /v1/avatar/sessions -> {r.status_code}")
            if r.status_code != 201:
                print("error body:", r.text[:300].replace(os.environ["BOSON_API_KEY"], "***"))
                return 1
            session_id = r.json()["id"]
            print(f"session id {session_id} status {r.json().get('status')}")
            out = DataStreamAudioOutput(
                room,
                destination_identity=AVATAR_IDENTITY,
                sample_rate=SAMPLE_RATE,
                wait_remote_track=rtc.TrackKind.KIND_AUDIO,
            )
            pcm = _sine(2.0)
            step = SAMPLE_RATE // 50 * 2  # 20 ms
            for i in range(0, len(pcm), step):
                chunk = pcm[i : i + step]
                await out.capture_frame(rtc.AudioFrame(chunk, SAMPLE_RATE, 1, len(chunk) // 2))
            out.flush()
            try:
                await asyncio.wait_for(video_seen.wait(), VIDEO_WAIT_S)
                video = True
            except TimeoutError:
                pass
            print(f"avatar video track seen: {'yes' if video else 'no'}")
        finally:
            if session_id:
                d = await http.delete(f"{BOSON_URL}/{session_id}", headers=headers)
                print(f"DELETE session -> {d.status_code}")
            await room.disconnect()
    return 0 if video else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
