"""Offline gate for the repo's own conventions, so `pytest -m "not live"` checks something real."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FACT_ROW = re.compile(r"^\| (F\d+) \|(.*)$", re.MULTILINE)
FACT_TAG = re.compile(r"VERIFIED-(DOCS|RUN) \(\d{4}-\d{2}-\d{2}\)")
INSIGHTS_SECTIONS = [
    "What Works",
    "What Doesn't Work",
    "Codebase Patterns",
    "Tool & Library Notes",
    "Recurring Errors & Fixes",
    "Session Notes",
    "Open Questions",
]


def _fact_rows() -> dict[str, str]:
    text = (ROOT / "docs" / "boson-protocol.md").read_text()
    return {fact_id: rest for fact_id, rest in FACT_ROW.findall(text)}


def test_every_protocol_fact_has_source_and_tag() -> None:
    rows = _fact_rows()
    assert len(rows) >= 13, f"expected F1..F13, found {sorted(rows)}"
    for fact_id, row in rows.items():
        assert "https://" in row, f"{fact_id} has no source URL"
        assert FACT_TAG.search(row), f"{fact_id} has no VERIFIED-DOCS/RUN (date) tag"


def test_agent_guard_matches_offline_checks_in_claude_md() -> None:
    guard = json.loads((ROOT / ".claude" / "agent-guard.json").read_text())["checkCommands"]
    claude = (ROOT / "CLAUDE.md").read_text()
    check_section = claude.split("## Check", 1)[1].split("\n## ", 1)[0]
    offline = [
        m.group(1)
        for line in check_section.splitlines()
        if line.rstrip().endswith("| none |")
        for m in [re.search(r"`([^`]+)`", line)]
        if m
    ]
    assert offline == guard


def test_agents_md_is_a_symlink_to_claude_md() -> None:
    agents = ROOT / "AGENTS.md"
    assert agents.is_symlink()
    assert agents.resolve() == (ROOT / "CLAUDE.md").resolve()


def test_insights_has_the_fixed_sections_in_order() -> None:
    text = (ROOT / "factory" / "INSIGHTS.md").read_text()
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert headings == INSIGHTS_SECTIONS
