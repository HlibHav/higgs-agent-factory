"""Line data for the demo film: the screenplay in machine form (AC-43).

`docs/demo-film/lines.json` is the one source for the claims gate (lane A), the captions and the
graphics (lane B). These tests hold it to `docs/demo-film/screenplay.md` word for word, to
`docs/CLAIMS.md` row names, and to the generated `film-data.schema.json`.
"""

import json
import re
from pathlib import Path

import pytest

from factory.film.line_data import (
    LINES_PATH,
    LineData,
    Timeline,
    load_lines,
)

ROOT = Path(__file__).resolve().parents[1]
SCREENPLAY = ROOT / "docs" / "demo-film" / "screenplay.md"
SCHEMA = ROOT / "docs" / "demo-film" / "film-data.schema.json"
CLAIMS = ROOT / "docs" / "CLAIMS.md"

NUMBER_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety hundred thousand million once twice"
).split()
NUMBER_TOKEN = re.compile(r"\d+|\b(?:" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)
ID_PATTERNS = (re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{6,8}"), re.compile(r"brief-[a-z0-9-]+"))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def _beat_rows() -> dict[int, list[str]]:
    rows: dict[int, list[str]] = {}
    for line in SCREENPLAY.read_text().splitlines():
        m = re.match(r"\|\s*(\d)\. [^|]+\|", line)
        if m:
            rows[int(m.group(1))] = [c.strip() for c in line.strip().strip("|").split("|")]
    return rows


def _voice_sentences(number: int, voice: str) -> str:
    if number == 7:
        return " ".join(re.findall(r'\*"(.+?)"\*', voice))
    m = re.fullmatch(r'\*"(.+)"\*', voice)
    assert m, f"beat {number} voice cell is not one quoted italic span"
    return m.group(1)


def _end_card_paragraph() -> str:
    text = SCREENPLAY.read_text()
    section = text.split("### End card", 1)[1].split("\n", 1)[1]
    return _clean(section.strip().split("\n\n", 1)[0])


def _claim_rows() -> set[str]:
    rows = set()
    for line in CLAIMS.read_text().splitlines():
        if line.startswith("| ") and not line.startswith("| claim") and "---" not in line[:6]:
            rows.add(line.split("|")[1].strip())
    return rows


def _all_lines(data: LineData) -> dict[str, str]:
    """line_id -> text for every narrator line, graphic item and end-card item."""
    out: dict[str, str] = {}
    for beat in data.beats:
        for n in beat.narrator:
            out[n.id] = n.text
    for g in data.graphics:
        for item in g.items:
            out[f"{g.id}/{item.id}"] = item.text
    return out


@pytest.fixture(scope="module")
def data() -> LineData:
    return load_lines()


def test_lines_json_validates(data: LineData) -> None:
    raw = json.loads(LINES_PATH.read_text())
    assert LineData.model_validate(raw) == data
    assert data.schema_version == 1
    assert [b.number for b in data.beats] == list(range(1, 9))


def test_lines_match_screenplay_word_for_word(data: LineData) -> None:
    rows = _beat_rows()
    assert sorted(rows) == list(range(1, 9))
    for beat in data.beats:
        _, time, picture, voice = rows[beat.number]
        start, end = (float(x) for x in re.split(r"[–-]", time))
        assert beat.target_s == end - start, f"beat {beat.number} target"
        spoken = " ".join(n.text for n in beat.narrator)
        assert spoken == _voice_sentences(beat.number, voice), f"beat {beat.number} narrator"
        for g in (g for g in data.graphics if g.beat == beat.number and g.id != "end-card"):
            for item in g.items:
                assert item.text in _clean(picture), f"{g.id}/{item.id} not in beat {beat.number}"
    beat7 = next(b for b in data.beats if b.number == 7)
    assert [n.id for n in beat7.narrator] == ["b7-intro", "b7-outro"]

    table = SCREENPLAY.read_text().split("### Beat 7 dialogue", 1)[1]
    said = re.findall(r"\| Trainee, (T[12]) \| \*\"(.+?)\"\* \|", table)
    assert [(d.id, d.text) for d in data.dialogue] == said
    assert len(said) == 2

    end_card = next(g for g in data.graphics if g.id == "end-card")
    assert " · ".join(i.text for i in end_card.items) == _end_card_paragraph()


def test_schema_file_matches_models() -> None:
    expected = {
        "LineData": LineData.model_json_schema(),
        "Timeline": Timeline.model_json_schema(),
    }
    assert json.loads(SCHEMA.read_text()) == expected


def test_references_resolve(data: LineData) -> None:
    sentence_ids = {n.id for b in data.beats for n in b.narrator}
    assert len(sentence_ids) == sum(len(b.narrator) for b in data.beats)
    refs = [c.at_line for g in data.graphics for c in g.cues]
    refs += [g.starts_at_line for g in data.graphics if g.starts_at_line]
    refs += [i.at_line for b in data.beats for i in b.images]
    refs += [h.at_line for h in data.highlights]
    assert set(refs) <= sentence_ids
    assert {c.id for g in data.graphics for c in g.cues} == {
        "verdict-stamp",
        "boson-row",
        "two-lines",
    }
    end_card = next(g for g in data.graphics if g.id == "end-card")
    assert end_card.starts_at_line == "b8-s3"
    assert [(i.id, i.at_line) for i in next(b for b in data.beats if b.number == 8).images] == [
        ("ihbench-pr-2", "b8-s1"),
        ("boson-handoff", "b8-s2"),
    ]
    assert all(h.beat == 5 for h in data.highlights)
    assert {h.at_line for h in data.highlights} <= {n.id for n in data.beats[4].narrator}


def test_claim_mappings_use_real_rows_and_none_is_left_unmapped(data: LineData) -> None:
    lines = _all_lines(data)
    rows = _claim_rows()
    assert data.claims, "no claim mappings"
    for c in data.claims:
        assert c.line_id in lines, c
        assert c.phrase in lines[c.line_id], c
        assert c.row is not None, f"{c.line_id}: unmapped phrase {c.phrase!r}"
        assert c.row in rows, f"{c.line_id}: no CLAIMS row named {c.row!r}"


def test_market_and_templates_map_to_their_rows(data: LineData) -> None:
    by_line = {(c.line_id, c.row) for c in data.claims}
    market = (
        "Boson is the only one of six compared voice companies with its own "
        "speech-to-speech, TTS and real-time avatar"
    )
    assert ("b2-s2", market) in by_line
    five = [c for c in data.claims if c.line_id == "b3-s4"]
    assert [c.row for c in five] == ["Five templates ship"]


def test_exemptions_are_explicit_and_reasoned(data: LineData) -> None:
    lines = _all_lines(data)
    got = {(e.line_id, e.phrase) for e in data.exemptions}
    assert got == {
        ("b2-s1", "three layers"),
        ("b2-s3", "one question"),
        ("b4-s1", "one long prompt"),
        ("decision/line-2", "ONE TEMPLATE, ALL THE WAY"),
    }
    for e in data.exemptions:
        assert e.phrase in lines[e.line_id]
        assert len(e.reason.split()) >= 4, f"{e.line_id}: reason too thin"
    mapped = {(c.line_id, c.phrase) for c in data.claims}
    assert not (mapped & got), "a phrase is both mapped and exempt"


def test_every_number_token_is_mapped_or_exempt(data: LineData) -> None:
    """A data-level mirror of the claims gate: lane A's gate must find nothing here."""
    covered: dict[str, list[str]] = {}
    for c in data.claims:
        covered.setdefault(c.line_id, []).append(c.phrase)
    for e in data.exemptions:
        covered.setdefault(e.line_id, []).append(e.phrase)
    for line_id, text in _all_lines(data).items():
        spans = [
            m.span()
            for phrase in covered.get(line_id, [])
            for m in re.finditer(re.escape(phrase), text)
        ]
        id_spans = [m.span() for pat in ID_PATTERNS for m in pat.finditer(text)]
        for m in NUMBER_TOKEN.finditer(text):
            if any(s <= m.start() < e for s, e in id_spans):
                continue
            assert any(s <= m.start() and m.end() <= e for s, e in spans), (
                f"{line_id}: number {m.group()!r} in {text!r} is neither mapped nor exempt"
            )


def test_ids_shown_sit_inside_a_mapped_phrase_whose_row_holds_them(data: LineData) -> None:
    evidence: dict[str, str] = {}
    for line in CLAIMS.read_text().splitlines():
        if line.startswith("| ") and line.count("|") >= 6:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            evidence[cells[0]] = cells[2]
    for line_id, text in _all_lines(data).items():
        for pat in ID_PATTERNS:
            for m in pat.finditer(text):
                rows = [
                    c.row
                    for c in data.claims
                    if c.line_id == line_id and c.row and m.group() in c.phrase
                ]
                assert rows, f"{line_id}: id {m.group()} not inside a mapped phrase"
                assert any(m.group() in evidence[r] for r in rows), (
                    f"{line_id}: id {m.group()} not in the evidence of {rows}"
                )


def test_lane_b_gets_every_caption_text(data: LineData) -> None:
    assert data.interrupted_caption == "(interrupted)"
    for beat in data.beats:
        assert beat.narrator, f"beat {beat.number} has no narrator line to caption"
        assert all(n.text.strip() for n in beat.narrator)
    assert [d.id for d in data.dialogue] == ["T1", "T2"]


def test_timeline_carries_slots_and_captions() -> None:
    t = Timeline.model_validate(
        {
            "schema_version": 1,
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "total_frames": 5400,
            "graphics": [
                {"id": "hook", "frames": 330, "cues": [{"id": "verdict-stamp", "frame": 90}]}
            ],
            "captions": [
                {
                    "id": "b1-s1",
                    "kind": "narrator",
                    "text": "x",
                    "start_frame": 12,
                    "end_frame": 100,
                },
                {
                    "id": "T1-reply",
                    "kind": "interrupted",
                    "text": "(interrupted)",
                    "start_frame": 100,
                    "end_frame": 130,
                },
            ],
        }
    )
    assert t.graphics[0].frames == 330
    assert [c.kind for c in t.captions] == ["narrator", "interrupted"]
    with pytest.raises(ValueError):
        Timeline.model_validate({**t.model_dump(), "fps": 24})


def test_no_secret_shaped_text_in_lines(data: LineData) -> None:
    blob = LINES_PATH.read_text()
    assert not re.search(r"sk-[A-Za-z0-9]{8,}|BOSON_API_KEY|api[_-]?key", blob, re.IGNORECASE)
