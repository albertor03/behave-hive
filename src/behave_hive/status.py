"""Status mapping from behave to Cucumber (spec:reporting/Status mapping)."""

from __future__ import annotations

from behave.model_type import Status

STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "error": "failed",
    "hook_error": "failed",
    "cleanup_error": "failed",
    "xpassed": "failed",
    "skipped": "skipped",
    "untested": "skipped",
    "xfailed": "skipped",
    "undefined": "undefined",
    "untested_undefined": "undefined",
    "pending": "pending",
    "pending_warn": "pending",
    "untested_pending": "pending",
}


def map_status(status: str | Status) -> str:
    """Cucumber status for a behave one; anything unknown is `failed`."""
    name = status.name if isinstance(status, Status) else status
    return STATUS_MAP.get(name, "failed")


_RAN = ("passed", "pending_warn", "failed", "undefined", "pending")


def scenario_status(scenario, steps) -> str:
    """Cucumber status of a scenario, by the priority of spec:reporting/Scenario status.

    `scenario.status` is not used: behave turns `pending` and `undefined` into `error`.
    """
    if scenario.hook_failed or scenario.status.name == "cleanup_error":
        return "failed"
    raw = [step.status.name for step in steps]
    mapped = [map_status(name) for name in raw]
    if "failed" in mapped:
        return "failed"
    if "undefined" in mapped:
        return "undefined"
    if any(name in ("pending", "untested_pending") for name in raw):
        return "pending"
    if scenario.should_skip or not any(name in _RAN for name in raw):
        return "skipped"
    return "passed"
