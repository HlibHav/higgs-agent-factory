"""File-backed Eval Card store (adapter): <root>/<agent_id>/<run_id>.json, never overwritten."""

import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from factory.gate.records import EvalCard

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _check_id(value: str) -> str:
    """Ids become path parts; reject anything that could leave the store root."""
    if not _SAFE_ID.fullmatch(value) or ".." in value:
        raise ValueError(f"unsafe id for a card path: {value!r}")
    return value


def new_run_id(now: datetime) -> str:
    """`YYYYmmddTHHMMSSZ-<8 hex>`; the random tail keeps same-second runs distinct (AC-33)."""
    if now.tzinfo is not None:
        now = now.astimezone(UTC)
    return f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"


class FileCardStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, card: EvalCard) -> Path:
        agent_dir = self._root / _check_id(card.agent_id)
        path = agent_dir / f"{_check_id(card.run_id)}.json"
        agent_dir.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as f:  # "x": an earlier card is never overwritten
            f.write(card.model_dump_json(indent=2))
        return path

    def latest(self, agent_id: str) -> EvalCard | None:
        agent_dir = self._root / _check_id(agent_id)
        if not agent_dir.is_dir():
            return None
        newest: EvalCard | None = None
        for p in agent_dir.glob("*.json"):
            try:
                card = EvalCard.model_validate_json(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # an unreadable card is skipped, not fatal
            if newest is None or (card.ended_at, card.run_id) > (newest.ended_at, newest.run_id):
                newest = card
        return newest
