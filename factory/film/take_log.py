"""The take log: one JSON line per take, append-only, plus the keeper mark (AC-25, AC-30,
AC-59).

Transcripts are data from the agent: they are stored as JSON strings and never judged here
(Glib judges by ear whether the reply refuses and offers to go back to the policy).
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter

from factory.film.takes import TakeVerdict

NONE: Literal["none"] = "none"


class TakeEntry(BaseModel):
    kind: Literal["take"] = "take"
    take: int
    started_at: str
    status: Literal["candidate", "dropped"]
    reasons: list[str] | Literal["none"]
    t2_split: str
    t2_offset_s: float | Literal["none"]
    stop_latency_ms: float | Literal["none"]
    t2_transcript: str
    ttfa: list[dict[str, Any]] | Literal["none"]
    end_reason: str


class KeeperMark(BaseModel):
    kind: Literal["keeper"] = "keeper"
    take: int
    at: str


class KeeperRefused(Exception):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry_from(verdict: TakeVerdict, take: int, started_at: datetime) -> TakeEntry:
    """Every field is present: a missing value reads "none"."""
    return TakeEntry(
        take=take,
        started_at=_iso(started_at),
        status=verdict.status,
        reasons=verdict.reasons or NONE,
        t2_split=NONE if verdict.split_n is None else f"T2 split into {verdict.split_n} responses",
        t2_offset_s=NONE if verdict.t2_offset_s is None else verdict.t2_offset_s,
        stop_latency_ms=NONE if verdict.stop_latency_ms is None else verdict.stop_latency_ms,
        t2_transcript=verdict.t2_transcript or NONE,
        ttfa=[{"ms": ms, "label": label} for ms, label in verdict.ttfa] or NONE,
        end_reason=verdict.end_reason or NONE,
    )


_LINE = TypeAdapter(TakeEntry | KeeperMark)


class TakeLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def _append_line(self, line: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def append(self, entry: TakeEntry) -> None:
        self._append_line(entry.model_dump_json())

    def _records(self) -> list[TakeEntry | KeeperMark]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        return [_LINE.validate_json(line) for line in text.splitlines() if line.strip()]

    def entries(self) -> list[TakeEntry]:
        return [r for r in self._records() if isinstance(r, TakeEntry)]

    def mark_keeper(self, take: int, now: Callable[[], datetime]) -> KeeperMark:
        """AC-59: record the mark when the take is a candidate; refuse a dropped take and name
        its reasons."""
        entry = next((e for e in self.entries() if e.take == take), None)
        if entry is None:
            raise KeeperRefused([f"no take {take} in the log"])
        if entry.status != "candidate":
            reasons = entry.reasons if isinstance(entry.reasons, list) else ["dropped"]
            raise KeeperRefused(list(reasons))
        mark = KeeperMark(take=take, at=_iso(now()))
        self._append_line(mark.model_dump_json())
        return mark

    def keeper(self) -> TakeEntry | None:
        """The take of the latest keeper mark."""
        marks = [r for r in self._records() if isinstance(r, KeeperMark)]
        if not marks:
            return None
        return next((e for e in self.entries() if e.take == marks[-1].take), None)
