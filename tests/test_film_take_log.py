"""Take log and keeper mark (AC-25, AC-30, AC-59)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factory.film.take_log import KeeperRefused, TakeEntry, TakeLog, entry_from
from factory.film.takes import TakeVerdict

NOW = datetime(2026, 10, 24, 18, 30, 5, tzinfo=UTC)


def _candidate(**kw: object) -> TakeVerdict:
    base: dict[str, object] = {
        "status": "candidate",
        "reasons": [],
        "t2_offset_s": 1.5,
        "stop_latency_ms": 220.0,
        "t2_transcript": "I can't share that.",
        "ttfa": [(800.0, "speech_stopped to first audio delta")],
    }
    base.update(kw)
    return TakeVerdict(**base)  # type: ignore[arg-type]


def test_log_is_append_only_jsonl(tmp_path: Path) -> None:
    log = TakeLog(tmp_path / "runs" / "r1" / "takes.jsonl")
    log.append(entry_from(_candidate(), 1, NOW))
    first_line = (tmp_path / "runs" / "r1" / "takes.jsonl").read_text().splitlines()[0]
    log.append(entry_from(_candidate(), 2, NOW))
    lines = (tmp_path / "runs" / "r1" / "takes.jsonl").read_text().splitlines()
    assert len(lines) == 2 and lines[0] == first_line
    assert [e.take for e in log.entries()] == [1, 2]


def test_entry_has_every_field_or_none() -> None:
    e = entry_from(_candidate(), 3, NOW)
    assert e.started_at == "2026-10-24T18:30:05Z"
    assert (e.kind, e.take, e.status) == ("take", 3, "candidate")
    assert e.reasons == "none" and e.t2_split == "none" and e.end_reason == "none"
    assert e.t2_offset_s == 1.5 and e.stop_latency_ms == 220.0
    assert e.ttfa == [{"ms": 800.0, "label": "speech_stopped to first audio delta"}]
    bare = entry_from(TakeVerdict(status="dropped", reasons=["no reply to T1"]), 1, NOW)
    dumped = bare.model_dump()
    assert dumped["reasons"] == ["no reply to T1"]
    for key in (
        "t2_split",
        "t2_offset_s",
        "stop_latency_ms",
        "t2_transcript",
        "ttfa",
        "end_reason",
    ):
        assert dumped[key] == "none", key
    split = entry_from(_candidate(split_n=2, end_reason="closed"), 1, NOW)
    assert split.t2_split == "T2 split into 2 responses" and split.end_reason == "closed"
    blank = entry_from(_candidate(t2_transcript=None), 1, NOW)
    assert blank.t2_transcript == "none"


def test_t2_transcript_logged_no_verdict(tmp_path: Path) -> None:
    text = 'Not that. {\\b1}<b>x</b> "quoted"\nsecond line'
    log = TakeLog(tmp_path / "takes.jsonl")
    log.append(entry_from(_candidate(t2_transcript=text), 1, NOW))
    raw = (tmp_path / "takes.jsonl").read_text()
    assert len(raw.splitlines()) == 1  # newlines are JSON-escaped
    parsed = json.loads(raw)
    assert parsed["t2_transcript"] == text  # recorded verbatim, as data
    assert not ({"refuses", "policy", "verdict", "offers_policy"} & set(parsed))


def test_keeper_mark_candidate_recorded_dropped_refused(tmp_path: Path) -> None:
    log = TakeLog(tmp_path / "takes.jsonl")
    log.append(entry_from(_candidate(), 1, NOW))
    log.append(entry_from(TakeVerdict(status="dropped", reasons=["no reply to T1", "x"]), 2, NOW))
    assert log.keeper() is None
    mark = log.mark_keeper(1, lambda: NOW)
    assert (mark.kind, mark.take, mark.at) == ("keeper", 1, "2026-10-24T18:30:05Z")
    keeper = log.keeper()
    assert isinstance(keeper, TakeEntry) and keeper.take == 1
    with pytest.raises(KeeperRefused) as info:
        log.mark_keeper(2, lambda: NOW)
    assert info.value.reasons == ["no reply to T1", "x"]
    with pytest.raises(KeeperRefused, match="no take 9"):
        log.mark_keeper(9, lambda: NOW)
    assert log.keeper() is not None and log.keeper().take == 1  # type: ignore[union-attr]
    assert [e.take for e in log.entries()] == [1, 2]  # marks are not entries


def test_missing_log_is_empty(tmp_path: Path) -> None:
    log = TakeLog(tmp_path / "none.jsonl")
    assert log.entries() == [] and log.keeper() is None
