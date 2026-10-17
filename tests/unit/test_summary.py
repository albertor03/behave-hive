import pytest

from behave_hive.merge import Report
from behave_hive.summary import exit_code, format_summary, summarize


def step(status):
    return {"keyword": "Given ", "name": "x", "line": 1, "result": {"status": status, "duration": 0}}


def scenario(status, steps):
    return {
        "type": "scenario",
        "id": "x",
        "line": 1,
        "steps": [step(s) for s in steps],
        "x-behave-hive": {"status": status, "behave_status": status},
    }


def background(steps):
    return {"type": "background", "line": 1, "steps": [step(s) for s in steps]}


def report(*features):
    return Report([{"uri": f"f{i}.feature", "elements": list(elements)} for i, elements in enumerate(features)])


def test_counts_features_scenarios_and_steps_by_status():
    r = report(
        [scenario("passed", ["passed", "passed"]), scenario("failed", ["passed", "failed", "skipped"])],
        [scenario("undefined", ["undefined"])],
    )
    s = summarize(r)
    assert s.features == 2
    assert s.scenarios == {"passed": 1, "failed": 1, "undefined": 1}
    assert s.steps == {"passed": 3, "failed": 1, "skipped": 1, "undefined": 1}


def test_backgrounds_are_not_scenarios_but_their_steps_are_counted():
    r = report([background(["passed"]), scenario("passed", ["passed"])])
    s = summarize(r)
    assert sum(s.scenarios.values()) == 1
    assert s.steps == {"passed": 2}


def test_line_format():
    line = format_summary(summarize(report([scenario("passed", ["passed"]), scenario("failed", ["failed"])])), 8.43)
    assert line == "1 feature · 2 scenarios (1 passed, 1 failed) · 2 steps (1 passed, 1 failed) · 8.4s"


def test_line_format_plural_and_all_passed():
    r = report([scenario("passed", ["passed"])] * 3, [scenario("passed", ["passed", "passed"])] * 3)
    assert format_summary(summarize(r), 0.04) == "2 features · 6 scenarios (6 passed) · 9 steps (9 passed) · 0.0s"


def test_line_format_status_order_is_fixed_and_zero_counts_are_omitted():
    r = report([scenario("skipped", ["skipped"]), scenario("pending", ["pending"]), scenario("passed", ["passed"])])
    assert "3 scenarios (1 passed, 1 pending, 1 skipped)" in format_summary(summarize(r), 1.0)


def test_empty_report():
    assert format_summary(summarize(Report([])), 0.0) == "0 features · 0 scenarios · 0 steps · 0.0s"


@pytest.mark.parametrize(
    "statuses, errors, code",
    [
        (["passed", "skipped"], 0, 0),
        ([], 0, 0),
        (["passed", "failed"], 0, 1),
        (["undefined"], 0, 1),
        (["pending"], 0, 1),
        (["passed"], 1, 1),
        (["skipped"], 0, 0),
    ],
)
def test_exit_code(statuses, errors, code):
    r = report([scenario(s, ["passed"]) for s in statuses])
    assert exit_code(summarize(r), batch_errors=errors) == code
