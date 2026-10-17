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
