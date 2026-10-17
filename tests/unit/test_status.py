import pytest
from behave.model_type import Status

from behave_hive.status import map_status

TABLE = {
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


@pytest.mark.parametrize("status", list(Status), ids=lambda s: s.name)
def test_map_status_for_every_behave_status(status):
    assert map_status(status.name) == TABLE.get(status.name, "failed")


def test_map_status_accepts_the_enum_member_too():
    assert map_status(Status.pending_warn) == "pending"


@pytest.mark.parametrize("unknown", ["bogus", "", "PASSED"])
def test_map_status_unknown_value_is_failed(unknown):
    assert map_status(unknown) == "failed"
