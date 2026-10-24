"""Verdict (domain). Decided from scenario labels and run completion only (AC-19)."""

from factory.gate.records import FailingScenario, GateRunRecord, Verdict

# AC-12 names these "failing rubric lines"; lane 0's FailingScenario is the card's shape for them.
FailingLine = FailingScenario


def decide_verdict(record: GateRunRecord) -> tuple[Verdict, list[FailingScenario]]:
    """A cut-short run is `incomplete`; any PARTIAL/FAIL is `rejected`; all PASS is `released`.

    Fails closed: an empty run, or a scenario with no judgment but no named cause, is never
    `released`. Takes no metrics argument, so RQ, TTFA and barge-in cannot change it (AC-19).
    """
    if record.cause is not None:
        return "incomplete", []
    if not record.scenarios or any(s.judgment is None for s in record.scenarios):
        return "incomplete", []
    failing = [
        FailingScenario(
            scenario_id=s.scenario_id,
            label=s.judgment.label,
            rubric=s.rubric,
            rationale=s.judgment.rationale,
            evidence=s.judgment.evidence,
        )
        for s in record.scenarios
        if s.judgment is not None and s.judgment.label != "PASS"
    ]
    if failing:
        return "rejected", failing
    return "released", []
