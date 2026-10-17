"""Opens a rendered report in headless Chromium and exercises the toolbar (task 5.12)."""
import base64

import pytest

from behave_hive.html_report import render
from behave_hive.merge import Report
from behave_hive.summary import summarize

pytestmark = pytest.mark.e2e
sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

PNG = base64.b64encode(
    base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
).decode()


def step(status="passed", error=None, embeddings=None):
    result = {"status": status, "duration": 300_000_000}
    if error:
        result["error_message"] = error
    data = {"keyword": "Given ", "name": "a step", "line": 3, "result": result}
    if embeddings:
        data["embeddings"] = embeddings
    return data


def scenario(name, status, tags=(), steps=None, line=3):
    return {
        "id": f"f;{name}", "keyword": "Scenario", "name": name, "description": "", "line": line, "type": "scenario",
        "tags": [{"name": t, "line": 1} for t in tags],
        "steps": steps or [step(status if status != "skipped" else "skipped")],
        "x-behave-hive": {"status": status, "behave_status": status},
    }


@pytest.fixture
def page(tmp_path):
    features = [
        {
            "uri": "features/a.feature", "id": "a", "keyword": "Feature", "name": "Login", "description": "", "line": 1,
            "tags": [],
            "elements": [
                scenario("admin ok", "passed", ("@smoke",), line=3),
                scenario(
                    "admin bad", "failed", ("@smoke", "@web"),
                    [step("failed", "boom", [{"mime_type": "image/png", "data": PNG}])], line=5,
                ),
                scenario("guest ok", "passed", ("@web",), line=7),
            ],
        },
        {
            "uri": "features/b.feature", "id": "b", "keyword": "Feature", "name": "Other", "description": "", "line": 1,
            "tags": [], "elements": [scenario("other ok", "passed", (), line=3)],
        },
    ]
    report = Report(features)
    path = tmp_path / "report.html"
    path.write_text(render(report, summarize(report), 3.2), encoding="utf-8")
    requests = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1200, "height": 900})
        tab = context.new_page()
        tab.on("request", lambda r: requests.append(r.url))
        tab.goto(path.as_uri())
        tab.requests = requests
        tab.screenshot_path = tmp_path / "report.png"
        yield tab
        browser.close()


def visible(page):
    return page.locator("details.scenario:not([hidden])").count()


def test_the_toolbar_is_shown_when_javascript_runs(page):
    assert page.locator(".toolbar").is_visible()
    assert page.locator("#shown").inner_text() == "Showing 4 of 4"


def test_filter_by_status_keeps_the_feature_table_totals(page):
    page.select_option("#status-filter", "failed")
    assert visible(page) == 1
    assert page.locator("section.feature:not([hidden])").count() == 1
    assert page.locator("tr.totals-row td").first.inner_text() == "4"


def test_filter_by_tag(page):
    page.select_option("#tag-filter", "@web")
    assert visible(page) == 2


def test_search_by_name_combined_with_tag_and_reset(page):
    page.fill("#search", "admin")
    page.select_option("#tag-filter", "@smoke")
    assert visible(page) == 2
    page.select_option("#status-filter", "failed")
    assert visible(page) == 1
    page.click("#reset")
    assert visible(page) == 4
    assert page.locator("#search").input_value() == ""


def test_expand_and_collapse_all(page):
    page.click("#expand-all")
    assert page.locator("details.scenario[open]").count() == 4
    page.click("#collapse-all")
    assert page.locator("details.scenario[open]").count() == 0


def test_screenshot_is_shown_and_can_be_enlarged(page):
    page.click("#expand-all")
    image = page.locator("label.zoom img")
    assert image.count() == 1
    assert image.evaluate("el => el.complete && el.naturalWidth > 0")
    page.click("label.zoom")
    assert page.locator("label.zoom input").is_checked()


def test_no_network_requests_beyond_the_file_itself(page):
    assert all(url.startswith("file://") or url.startswith("data:") for url in page.requests)
    page.screenshot(path=str(page.screenshot_path), full_page=True)
