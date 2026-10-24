"""Smallest live check of Higgs Realtime facts F1, F2 and F5 (docs/boson-protocol.md).

One text-only turn with a 16-token output cap: well under $0.01 at F12 rates.
Run: `uv run python scripts/smoke.py` or `uv run pytest -m live scripts/smoke.py`.
Every received event is written to results/smoke-<utc>.jsonl as evidence.
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import websockets

log = logging.getLogger("smoke")

ROOT = Path(__file__).resolve().parent.parent
URL = "wss://api.boson.ai/v1/realtime"  # F1: model is named in session.update, not the URL
QUIET_BEFORE_UPDATE_S = 3.0
TAIL_AFTER_DONE_S = 3.0
TURN_TIMEOUT_S = 30.0


def _api_key() -> str:
    key = os.environ.get("BOSON_API_KEY", "")
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "BOSON_API_KEY":
                key = value.strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("BOSON_API_KEY is not set (env or .env)")
    return key


async def run_smoke() -> dict:
    events: list[dict] = []
    findings: dict = {}
    headers = {"Authorization": f"Bearer {_api_key()}"}

    async with websockets.connect(URL, additional_headers=headers) as ws:

        async def recv(timeout: float) -> dict | None:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout)
            except TimeoutError:
                return None
            event = json.loads(raw)
            events.append(event)
            return event

        # F1: the server stays silent until the first session.update.
        early = await recv(QUIET_BEFORE_UPDATE_S)
        findings["event_before_session_update"] = early["type"] if early else None

        await ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "model": "higgs-realtime",
                        "output_modalities": ["text"],
                        "instructions": "Reply with exactly one word.",
                        "max_output_tokens": 16,
                        "audio": {"input": {"turn_detection": None}},
                    },
                }
            )
        )
        acks: list[str] = []
        while not {"session.created", "session.updated"} & set(acks):
            event = await recv(TURN_TIMEOUT_S)
            if event is None or event["type"] == "error":
                raise RuntimeError(f"session.update not acknowledged: {event}")
            acks.append(event["type"])
        findings["first_events_after_session_update"] = acks

        await ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Say OK."}],
                    },
                }
            )
        )
        await ws.send(json.dumps({"type": "response.create"}))

        done = None
        while done is None:
            event = await recv(TURN_TIMEOUT_S)
            if event is None:
                raise RuntimeError("no response.done within timeout")
            if event["type"] == "error":
                raise RuntimeError(f"server error: {event}")
            if event["type"] == "response.done":
                done = event
        response = done.get("response", {})
        findings["response_done_status"] = response.get("status")
        findings["response_done_usage"] = response.get("usage", "<missing>")
        findings["response_done_status_details"] = response.get("status_details", "<missing>")

        while await recv(TAIL_AFTER_DONE_S) is not None:
            pass
        findings["event_types_seen"] = sorted({e["type"] for e in events})
        findings["conversation_item_done_seen"] = any(
            e["type"] == "conversation.item.done" for e in events
        )

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"smoke-{stamp}.jsonl"
    out.write_text("".join(json.dumps(e) + "\n" for e in events))
    findings["evidence_file"] = str(out.relative_to(ROOT))
    return findings


@pytest.mark.live
def test_realtime_smoke() -> None:
    findings = asyncio.run(run_smoke())
    assert findings["event_before_session_update"] is None  # F1
    assert "session.created" in findings["first_events_after_session_update"]  # F1
    assert findings["response_done_usage"] is None  # F2
    assert findings["response_done_status_details"] is None  # F2
    assert findings["conversation_item_done_seen"] is False  # F5


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info(json.dumps(asyncio.run(run_smoke()), indent=2))
