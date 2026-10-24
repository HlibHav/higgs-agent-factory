"""Eval Card diff (domain, AC-78): what changed between a card and its coached successor."""

from pydantic import BaseModel, ConfigDict

from factory.gate.records import EvalCard


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Change(_Strict):
    key: str
    before: str | None
    after: str | None

    @property
    def changed(self) -> bool:
        return self.before != self.after


class CardDiff(_Strict):
    before_run_id: str
    after_run_id: str
    verdict: Change
    skills: list[Change]  # key = skill id, value = "passed/run"
    scenarios: list[Change]  # key = scenario id, value = label (with "disagreed" when so)
    metrics: list[Change]  # TTFA p50/p95, barge-in p50, estimated audio cost


def _label(card: EvalCard) -> dict[str, str]:
    out = {}
    for sc in card.scenarios:
        if sc.judgment is None:
            out[sc.scenario_id] = "no judgment"
        else:
            out[sc.scenario_id] = sc.judgment.label + (
                " (judge disagreed)" if sc.judge_agreed is False else ""
            )
    return out


def _ms(v: float | None) -> str | None:
    return None if v is None else f"{v:.0f} ms"


def _usd(v: float | None) -> str | None:
    return None if v is None else f"${v:.4f}"


def diff_cards(before: EvalCard, after: EvalCard) -> CardDiff:
    b_sk = {s.skill_id: f"{s.passed}/{s.scenarios_run}" for s in before.skills}
    a_sk = {s.skill_id: f"{s.passed}/{s.scenarios_run}" for s in after.skills}
    b_sc, a_sc = _label(before), _label(after)
    return CardDiff(
        before_run_id=before.run_id,
        after_run_id=after.run_id,
        verdict=Change(key="verdict", before=before.verdict, after=after.verdict),
        skills=[Change(key=k, before=b_sk.get(k), after=a_sk.get(k)) for k in {**b_sk, **a_sk}],
        scenarios=[Change(key=k, before=b_sc.get(k), after=a_sc.get(k)) for k in {**b_sc, **a_sc}],
        metrics=[
            Change(key="TTFA p50", before=_ms(before.ttfa_p50_ms), after=_ms(after.ttfa_p50_ms)),
            Change(key="TTFA p95", before=_ms(before.ttfa_p95_ms), after=_ms(after.ttfa_p95_ms)),
            Change(
                key="barge-in p50",
                before=_ms(before.bargein_p50_ms),
                after=_ms(after.bargein_p50_ms),
            ),
            Change(
                key="estimated audio cost",
                before=_usd(before.estimated_audio_cost_usd),
                after=_usd(after.estimated_audio_cost_usd),
            ),
        ],
    )


def render_diff_text(diff: CardDiff) -> str:
    lines = [f"Eval Card diff: {diff.before_run_id} -> {diff.after_run_id}"]
    for group, rows in (
        ("Verdict", [diff.verdict]),
        ("Skills (PASS/run)", diff.skills),
        ("Scenarios", diff.scenarios),
        ("Metrics (informational)", diff.metrics),
    ):
        lines.append(group + ":")
        for c in rows:
            mark = "*" if c.changed else " "
            lines.append(f" {mark} {c.key}: {c.before or '-'} -> {c.after or '-'}")
    return "\n".join(lines)
