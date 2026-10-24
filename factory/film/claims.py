"""Claims gate: every number, run id and agent id the film says or shows must map to an `ok`
row of `docs/CLAIMS.md` (AC-43, AC-47..AC-50).

Domain: stdlib and the line data only. The register text is passed in; `CLAIMS_PATH` says where
the default lives. Dialogue (T1, T2) is not gated: it is the trainee's voice, not a claim.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from factory.film.line_data import LineData

CLAIMS_PATH = Path(__file__).resolve().parents[2] / "docs" / "CLAIMS.md"

_RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
_AGENT_ID = re.compile(r"brief-[a-z0-9]+(?:-[a-z0-9]+)*")
_DIGITS = r"\d+(?:[.,:]\d+)*"
_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety hundred thousand million once twice"
).split()
_UNITS = "cents? euros? dollars? minutes? seconds? hours? percent".split()
_NUMBER = re.compile(
    rf"(?:\b(?:a|an)\s+(?:{'|'.join(_UNITS)})\b)|(?:\b(?:{'|'.join(_WORDS)})\b)|(?:{_DIGITS})",
    re.IGNORECASE,
)
_OK_NOTE = re.compile(r"^ok \(.+\)$")


@dataclass(frozen=True)
class ClaimRow:
    claim: str
    evidence: str
    status: str


@dataclass(frozen=True)
class ClaimFailure:
    line_id: str
    text: str
    found: str
    reason: str


@dataclass(frozen=True)
class GateResult:
    checked: list[str] = field(default_factory=list)
    failures: list[ClaimFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def parse_register(markdown: str) -> dict[str, ClaimRow]:
    """Rows of the CLAIMS table, keyed on the "claim" cell (the first)."""
    rows: dict[str, ClaimRow] = {}
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        if len(cells) < 5 or set(cells[0]) <= {"-", ":", " "} or cells[0] == "claim":
            continue
        rows[cells[0]] = ClaimRow(claim=cells[0], evidence=cells[2], status=cells[-1])
    return rows


def status_ok(status: str) -> bool:
    """`ok`, or `ok` followed by a note in parentheses. Nothing else passes (AC-48)."""
    s = status.strip()
    return s == "ok" or bool(_OK_NOTE.match(s))


def _mask_ids(text: str) -> str:
    def blank(m: re.Match[str]) -> str:
        return " " * len(m.group(0))

    return _AGENT_ID.sub(blank, _RUN_ID.sub(blank, text))


def _id_spans(text: str) -> list[tuple[int, int, str]]:
    found = [(m.start(), m.end(), m.group(0)) for m in _RUN_ID.finditer(text)]
    found += [(m.start(), m.end(), m.group(0)) for m in _AGENT_ID.finditer(text)]
    return sorted(found)


def _number_spans(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0)) for m in _NUMBER.finditer(_mask_ids(text))]


def find_numbers(text: str) -> list[str]:
    """Digits and English number words (AC-47); ids are cut out first and checked as ids."""
    return [s for _, _, s in _number_spans(text)]


def find_ids(text: str) -> list[str]:
    return [s for _, _, s in _id_spans(text)]


def _occurrences(text: str, phrase: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(re.escape(phrase), text, re.IGNORECASE)]


def _inside(span: tuple[int, int], outer: list[tuple[int, int]]) -> bool:
    return any(o[0] <= span[0] and span[1] <= o[1] for o in outer)


def _all_lines(lines: LineData) -> list[tuple[str, str]]:
    out = [(n.id, n.text) for b in lines.beats for n in b.narrator]
    out += [(f"{g.id}/{i.id}", i.text) for g in lines.graphics for i in g.items]
    return out


def run_claims_gate(lines: LineData, register: dict[str, ClaimRow]) -> GateResult:
    """Check every narrator line, graphic item and end-card item."""
    checked: list[str] = []
    failures: list[ClaimFailure] = []
    for line_id, text in _all_lines(lines):
        checked.append(line_id)
        mappings = [m for m in lines.claims if m.line_id == line_id]
        exempt = [
            sp
            for e in lines.exemptions
            if e.line_id == line_id
            for sp in _occurrences(text, e.phrase)
        ]

        def fail(found: str, reason: str, line_id: str = line_id, text: str = text) -> None:
            failures.append(ClaimFailure(line_id, text, found, reason))

        # Spans of mapped phrases whose row exists and is ok.
        good: list[tuple[int, int]] = []
        evidence_by_span: list[tuple[tuple[int, int], str]] = []
        bad: list[tuple[tuple[int, int], str]] = []
        for m in mappings:
            spans = _occurrences(text, m.phrase)
            if m.row is None:
                reason = f"phrase {m.phrase!r} is mapped to no CLAIMS row"
            elif m.row not in register:
                reason = f"no CLAIMS row {m.row!r}"
            elif not status_ok(register[m.row].status):
                reason = f"CLAIMS row {m.row!r} has status {register[m.row].status!r}, not ok"
            else:
                good += spans
                evidence_by_span += [(sp, register[m.row].evidence) for sp in spans]
                continue
            bad += [(sp, reason) for sp in spans]

        for start, end, token in _number_spans(text):
            span = (start, end)
            if _inside(span, exempt) or _inside(span, good):
                continue
            why = next((r for sp, r in bad if _inside(span, [sp])), None)
            fail(token, why or f"number {token!r} maps to no CLAIMS row")
        for start, end, token in _id_spans(text):
            span = (start, end)
            evidences = [ev for sp, ev in evidence_by_span if _inside(span, [sp])]
            if any(token in ev for ev in evidences):
                continue
            if evidences:
                fail(token, f"id {token!r} is not in the evidence of its mapped CLAIMS row")
            else:
                why = next((r for sp, r in bad if _inside(span, [sp])), None)
                fail(token, why or f"id {token!r} maps to no CLAIMS row")
    return GateResult(checked, failures)
