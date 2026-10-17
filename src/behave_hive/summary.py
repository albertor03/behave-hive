"""Final counters, summary line and exit code of a run (D8)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from behave_hive.merge import Report

STATUS_ORDER = ("passed", "failed", "undefined", "pending", "skipped")
FAILING = ("failed", "undefined", "pending")


@dataclass(frozen=True)
class Summary:
    features: int
    scenarios: dict[str, int] = field(default_factory=dict)
    steps: dict[str, int] = field(default_factory=dict)


def summarize(report: Report) -> Summary:
    """Scenarios by internal status (backgrounds excluded) and steps by result status."""
    scenarios: Counter[str] = Counter()
    steps: Counter[str] = Counter()
    for feature in report.features:
        for element in feature["elements"]:
            if element["type"] == "scenario":
                scenarios[element["x-behave-hive"]["status"]] += 1
            steps.update(step["result"]["status"] for step in element["steps"])
    return Summary(len(report.features), dict(scenarios), dict(steps))


def _part(count: int, noun: str, by_status: dict[str, int] | None = None) -> str:
    text = f"{count} {noun}{'' if count == 1 else 's'}"
    if by_status:
        detail = ", ".join(f"{by_status[s]} {s}" for s in STATUS_ORDER if by_status.get(s))
        text += f" ({detail})"
    return text


def format_summary(summary: Summary, duration: float) -> str:
    return " · ".join(
        [
            _part(summary.features, "feature"),
            _part(sum(summary.scenarios.values()), "scenario", summary.scenarios),
            _part(sum(summary.steps.values()), "step", summary.steps),
            f"{duration:.1f}s",
        ]
    )


def exit_code(summary: Summary, batch_errors: int = 0) -> int:
    """0 unless a scenario failed, is undefined or pending, or a batch had an infrastructure error."""
    if batch_errors or any(summary.scenarios.get(status) for status in FAILING):
        return 1
    return 0
