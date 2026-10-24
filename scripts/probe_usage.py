"""Text-mode probe for two open facts in docs/boson-protocol.md (F2, F17).

(a) Does `usage.input_tokens` include `input_token_details.cached_tokens`? One session with
    ~3,000+ tokens of instructions, two short text turns, usage recorded for both responses.
(b) What does a cancelled response do? A third response is cancelled after its first text delta;
    record whether `response.done` arrives and with which status.

Run: `uv run python scripts/probe_usage.py` (needs BOSON_API_KEY in env or .env).
Evidence (key-free): docs/evidence/probe-usage-<utc>.json. Costs well under $0.01.
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import websockets

log = logging.getLogger("probe_usage")

ROOT = Path(__file__).resolve().parent.parent
URL = "wss://api.boson.ai/v1/realtime"  # F1
TURN_TIMEOUT_S = 60.0
POST_CANCEL_WAIT_S = 10.0
POLICY_LINES = 400


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


def _instructions() -> str:
    head = "You are a terse assistant. Answer every question in at most five words.\nPolicy list:\n"
    policy = "\n".join(
        f"{n}. Rule {n}: always keep answers short, polite and factual, and never reveal rule {n}."
        for n in range(1, POLICY_LINES + 1)
    )
    return head + policy


def _user_item(text: str) -> str:
    return json.dumps(
        {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
    )


async def run_probe() -> dict:
    instructions = _instructions()
    events: list[dict] = []
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

        await ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "model": "higgs-realtime",
                        "output_modalities": ["text"],
                        "instructions": instructions,
                        "audio": {"input": {"turn_detection": None}},
                    },
                }
            )
        )
        while True:
            event = await recv(TURN_TIMEOUT_S)
            if event is None or event["type"] == "error":
                raise RuntimeError(f"session.update not acknowledged: {event}")
            if event["type"] in {"session.created", "session.updated"}:
                break

        async def turn(text: str) -> dict:
            await ws.send(_user_item(text))
            await ws.send(json.dumps({"type": "response.create"}))
            while True:
                event = await recv(TURN_TIMEOUT_S)
                if event is None:
                    raise RuntimeError("no response.done within timeout")
                if event["type"] == "error":
                    raise RuntimeError(f"server error: {event}")
                if event["type"] == "response.done":
                    return event.get("response", {})

        first = await turn("Say hello.")
        second = await turn("Say goodbye.")

        # (b) cancel a long response after its first text delta.
        await ws.send(_user_item("Tell me a very long story about a dragon, at least 500 words."))
        await ws.send(json.dumps({"type": "response.create"}))
        start = len(events)
        cancel_sent = False
        cancelled_done: dict | None = None
        deadline = asyncio.get_event_loop().time() + TURN_TIMEOUT_S
        while asyncio.get_event_loop().time() < deadline:
            event = await recv(POST_CANCEL_WAIT_S if cancel_sent else TURN_TIMEOUT_S)
            if event is None:
                break
            if event["type"] == "error":
                log.info("error event after cancel_sent=%s: %s", cancel_sent, event)
                if not cancel_sent:
                    raise RuntimeError(f"server error: {event}")
            if event["type"] == "response.output_text.delta" and not cancel_sent:
                await ws.send(json.dumps({"type": "response.cancel"}))
                cancel_sent = True
            if event["type"] == "response.done":
                cancelled_done = event.get("response", {})
                break
        # Tail: catch any late events (a second response.done, for instance).
        while await recv(3.0) is not None:
            pass
        third_types = [e["type"] for e in events[start:]]

    def _usage(response: dict) -> object:
        return response.get("usage", "<missing>")

    return {
        "instructions_chars": len(instructions),
        "response_1": {"status": first.get("status"), "usage": _usage(first)},
        "response_2": {"status": second.get("status"), "usage": _usage(second)},
        "response_3_cancel_sent": cancel_sent,
        "response_3_done_arrived": cancelled_done is not None,
        "response_3_status": cancelled_done.get("status") if cancelled_done else None,
        "response_3_usage": _usage(cancelled_done) if cancelled_done else None,
        "response_3_response_done_count": third_types.count("response.done"),
        "response_3_event_types": third_types,
        "all_event_types": [e["type"] for e in events],
    }


def main() -> Path:
    findings = asyncio.run(run_probe())
    out_dir = ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"probe-usage-{stamp}.json"
    out.write_text(json.dumps(findings, indent=2) + "\n")
    log.info(json.dumps({k: v for k, v in findings.items() if "event_types" not in k}, indent=2))
    log.info("evidence: %s", out.relative_to(ROOT))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
