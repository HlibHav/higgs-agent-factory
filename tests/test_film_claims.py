"""Claims gate (AC-43 coverage, AC-47..AC-50). Offline; the fixture is CLAIMS from before the
market row existed (`git show 225a457^:docs/CLAIMS.md`)."""

from pathlib import Path
from typing import Any

import pytest

from factory.film.claims import (
    CLAIMS_PATH,
    find_ids,
    find_numbers,
    parse_register,
    run_claims_gate,
    status_ok,
)
from factory.film.line_data import LineData, load_lines

FIXTURE = Path(__file__).parent / "fixtures" / "film" / "claims-2026-10-24.md"
MARKET_ROW = (
    "Boson is the only one of six compared voice companies with its own speech-to-speech, "
    "TTS and real-time avatar"
)

REGISTER_MD = """# Claim register

| claim | where used | evidence | honest phrasing | status |
|---|---|---|---|---|
| Good row | stage | Run `20261024T174839Z-6f4ab3b5`, agent `brief-demo-agent-ab12cd` | x | ok |
| Noted row | stage | evidence | say it | ok (as of today) |
| Measure row | stage | evidence | say it | measure |
| Okay-ish row | stage | evidence | say it | ok but not really |
"""


def _lines(
    narrator: list[tuple[str, str]],
    claims: list[tuple[str, str, str | None]] = (),  # type: ignore[assignment]
    exemptions: list[tuple[str, str]] = (),  # type: ignore[assignment]
    items: list[tuple[str, str]] = (),  # type: ignore[assignment]
) -> LineData:
    data: dict[str, Any] = {
        "schema_version": 1,
        "beats": [
            {
                "number": 1,
                "id": "hook",
                "target_s": 10,
                "picture": "graphic",
                "narrator": [{"id": i, "text": t} for i, t in narrator],
            }
        ],
        "dialogue": [{"id": "T1", "text": "eighty euros"}, {"id": "T2", "text": "two"}],
        "graphics": [
            {
                "id": "hook",
                "beat": 1,
                "starts_at_line": None,
                "items": [{"id": i.split("/")[1], "text": t} for i, t in items],
                "cues": [],
            }
        ],
        "claims": [{"line_id": a, "phrase": b, "row": c} for a, b, c in claims],
        "exemptions": [
            {"line_id": a, "phrase": b, "reason": "figure of speech"} for a, b in exemptions
        ],
        "highlights": [],
        "interrupted_caption": "(interrupted)",
    }
    return LineData.model_validate(data)


def test_find_numbers_ignores_articles() -> None:
    assert find_numbers("a voice agent") == []
    assert find_numbers("about a cent") == ["a cent"]
    assert find_numbers("k = 2") == ["2"]


def test_number_words_and_a_cent_unmapped_fail() -> None:
    assert find_numbers("Version one: four of six, twice, ONE TEMPLATE, a Hundred") == [
        "one",
        "four",
        "six",
        "twice",
        "ONE",
        "Hundred",
    ]
    assert find_numbers("someone is done, none, honest") == []
    assert find_numbers("for about an hour and 3.5 percent") == ["an hour", "3.5"]
    lines = _lines([("b1-s1", "It cost a cent."), ("b1-s2", "It is a voice agent.")])
    result = run_claims_gate(lines, parse_register(REGISTER_MD))
    assert [f.line_id for f in result.failures] == ["b1-s1"]
    assert result.failures[0].found == "a cent"
    assert not result.ok


def test_ids_cut_before_numbers() -> None:
    text = "run 20261024T174839Z-6f4ab3b5 done"
    assert find_ids(text) == ["20261024T174839Z-6f4ab3b5"]
    assert find_numbers(text) == []
    assert find_ids("agent brief-onboarding-buddy-b948ed is ok") == [
        "brief-onboarding-buddy-b948ed"
    ]


def test_status_ok_rules() -> None:
    assert status_ok("ok")
    assert status_ok("ok (as of 2026-10-24)")
    assert status_ok("ok (no numbers)")
    for bad in ("measure", "conversation-only", "do-not-use", "ok but not", "okay", "", "ok ()"):
        assert not status_ok(bad), bad
    register = parse_register(REGISTER_MD)
    assert set(register) == {"Good row", "Noted row", "Measure row", "Okay-ish row"}
    lines = _lines(
        [("b1-s1", "Four."), ("b1-s2", "Five."), ("b1-s3", "Six.")],
        [
            ("b1-s1", "Four", "Good row"),
            ("b1-s2", "Five", "Measure row"),
            ("b1-s3", "Six", "No such row"),
        ],
    )
    result = run_claims_gate(lines, register)
    assert [f.line_id for f in result.failures] == ["b1-s2", "b1-s3"]
    assert "measure" in result.failures[0].reason
    assert "no CLAIMS row" in result.failures[1].reason


def test_unmapped_row_none_fails() -> None:
    lines = _lines([("b1-s1", "Four.")], [("b1-s1", "Four", None)])
    assert [f.line_id for f in run_claims_gate(lines, parse_register(REGISTER_MD)).failures] == [
        "b1-s1"
    ]


def test_exemption_passes_number_word_only_inside_its_phrase() -> None:
    lines = _lines(
        [("b1-s1", "It is one question."), ("b1-s2", "It is one question and one more.")],
        exemptions=[("b1-s1", "one question"), ("b1-s2", "one question")],
    )
    result = run_claims_gate(lines, parse_register(REGISTER_MD))
    assert [(f.line_id, f.found) for f in result.failures] == [("b1-s2", "one")]


def test_run_id_must_be_in_mapped_row_evidence() -> None:
    register = parse_register(REGISTER_MD)
    ok = _lines(
        [("b1-s1", "Run 20261024T174839Z-6f4ab3b5 passed.")],
        [("b1-s1", "20261024T174839Z-6f4ab3b5", "Good row")],
    )
    assert run_claims_gate(ok, register).ok
    wrong = _lines(
        [("b1-s1", "Run 20261024T999999Z-deadbeef passed.")],
        [("b1-s1", "20261024T999999Z-deadbeef", "Good row")],
    )
    assert "not in the evidence" in run_claims_gate(wrong, register).failures[0].reason
    unmapped = _lines([("b1-s1", "Run 20261024T174839Z-6f4ab3b5 passed.")])
    assert not run_claims_gate(unmapped, register).ok
    agent = _lines(
        [("b1-s1", "Agent brief-demo-agent-ab12cd.")],
        [("b1-s1", "brief-demo-agent-ab12cd", "Good row")],
    )
    assert run_claims_gate(agent, register).ok


def test_market_line_fails_on_register_snapshot() -> None:
    lines = load_lines()
    old = parse_register(FIXTURE.read_text(encoding="utf-8"))
    assert MARKET_ROW not in old
    failed = {f.line_id for f in run_claims_gate(lines, old).failures}
    assert {"b2-s2", "end-card/market"} <= failed


def test_current_register_passes_every_line() -> None:
    lines = load_lines()
    current = parse_register(CLAIMS_PATH.read_text(encoding="utf-8"))
    result = run_claims_gate(lines, current)
    assert [(f.line_id, f.found, f.reason) for f in result.failures] == []


def test_gate_covers_every_line_and_graphic_item() -> None:
    lines = load_lines()
    result = run_claims_gate(lines, parse_register(CLAIMS_PATH.read_text(encoding="utf-8")))
    expected = [n.id for b in lines.beats for n in b.narrator]
    expected += [f"{g.id}/{i.id}" for g in lines.graphics for i in g.items]
    assert sorted(result.checked) == sorted(expected)
    texts = {n.id: n.text for b in lines.beats for n in b.narrator}
    texts |= {f"{g.id}/{i.id}": i.text for g in lines.graphics for i in g.items}
    for mapping in lines.claims:
        assert mapping.phrase.lower() in texts[mapping.line_id].lower(), mapping
    for exemption in lines.exemptions:
        assert exemption.phrase.lower() in texts[exemption.line_id].lower(), exemption


@pytest.mark.parametrize("line_id", ["T1", "T2"])
def test_dialogue_is_not_gated(line_id: str) -> None:
    lines = load_lines()
    result = run_claims_gate(lines, parse_register(CLAIMS_PATH.read_text(encoding="utf-8")))
    assert line_id not in result.checked
