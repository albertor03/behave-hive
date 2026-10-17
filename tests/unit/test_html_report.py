import re

from behave_hive.html_report import render
from behave_hive.merge import Report
from behave_hive.summary import summarize


def step(name="step", status="passed", duration=250_000_000, error=None):
    result = {"status": status, "duration": duration}
    if error:
        result["error_message"] = error
    return {"keyword": "Given ", "name": name, "line": 3, "result": result}


def scenario(name="S", status="passed", steps=None, source=None, line=3):
    ext = {"status": status, "behave_status": status}
    if source:
        ext["source"] = source
    return {
        "id": f"f;{name}-l{line}", "keyword": "Scenario", "name": name, "description": "", "line": line,
        "type": "scenario", "tags": [], "steps": steps or [step()], "x-behave-hive": ext,
    }


def feature(elements, name="Login", uri="features/login.feature"):
    return {"uri": uri, "id": "f", "keyword": "Feature", "name": name, "description": "", "line": 1, "tags": [], "elements": elements}


def html(features, duration=8.4):
    report = Report(features)
    return render(report, summarize(report), duration)


def test_shows_totals_and_duration():
    page = html([feature([scenario("A"), scenario("B", "failed", [step(status="failed", error="boom")])])])
    assert "1 feature · 2 scenarios (1 passed, 1 failed) · 2 steps (1 passed, 1 failed) · 8.4s" in page


def test_shows_features_scenarios_steps_and_error_message():
    page = html([feature([scenario("A", "failed", [step("open page", "failed", 1_500_000_000, "boom happened")])])])
    for text in ("Login", "features/login.feature", "A", "open page", "boom happened", "1.50s", "failed"):
        assert text in page


def test_shows_the_csv_source_next_to_the_scenario():
    source = {"csv_path": "features/data/login.csv", "csv_row": 3}
    assert "features/data/login.csv:3" in html([feature([scenario("A", source=source)])])


def test_scenario_without_source_shows_no_csv_reference():
    assert ".csv" not in html([feature([scenario("A")])])


def test_names_are_escaped():
    page = html([feature([scenario("<script>alert(1)</script>", steps=[step("<img src=x onerror=1>", "failed", error="<b>x</b>")])], name="<script>f</script>")])
    assert "<script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=1&gt;" in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_is_self_contained_without_external_urls_or_scripts():
    page = html([feature([scenario("A")])])
    assert not re.search(r"https?://", page)
    assert "<script" not in page.lower()
    assert "<link" not in page.lower()


def test_supports_dark_mode():
    assert "prefers-color-scheme: dark" in html([feature([scenario("A")])])


def test_is_a_complete_document_with_one_details_per_scenario():
    page = html([feature([scenario("A"), scenario("B")])])
    assert page.lstrip().lower().startswith("<!doctype html>")
    assert page.count("<details") == 2
    assert '<meta charset="utf-8">' in page


def test_empty_report_renders():
    assert "0 scenarios" in html([])
