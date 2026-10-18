"""Opens a rendered report in headless Chromium and exercises the toolbar (task 5.12)."""
import base64
import contextlib

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


def feature(name, uri, elements):
    return {
        "uri": uri, "id": uri, "keyword": "Feature", "name": name, "description": "", "line": 1, "tags": [],
        "elements": elements,
    }


def outline_row(n, status):
    row = scenario(f"Login -- @1.{n} ", status, ("@smoke",), line=10 + n)
    row["id"] = f"c;login-l9;;{n}"
    return row


@contextlib.contextmanager
def opened(tmp_path, features, fragment=""):
    report = Report(features)
    path = tmp_path / "report.html"
    path.write_text(render(report, summarize(report), 3.2), encoding="utf-8")
    requests = []
    policy_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1200, "height": 900}, permissions=["clipboard-read", "clipboard-write"]
        )
        tab = context.new_page()
        tab.on("request", lambda r: requests.append(r.url))
        tab.on("console", lambda msg: policy_errors.append(msg.text) if "Content Security Policy" in msg.text else None)
        tab.goto(path.as_uri() + fragment)
        tab.requests = requests
        tab.policy_errors = policy_errors
        tab.screenshot_path = tmp_path / "report.png"
        yield tab
        browser.close()


LOGIN_FEATURES = [
    feature("Login", "features/a.feature", [
        scenario("admin ok", "passed", ("@smoke",), line=3),
        scenario(
            "admin bad", "failed", ("@smoke", "@web"),
            [step("failed", "boom", [{"mime_type": "image/png", "data": PNG}])], line=5,
        ),
        scenario("guest ok", "passed", ("@web",), line=7),
    ]),
    feature("Other", "features/b.feature", [scenario("other ok", "passed", (), line=3)]),
]


@pytest.fixture
def page(tmp_path):
    with opened(tmp_path, LOGIN_FEATURES) as tab:
        yield tab


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


def test_csp_allows_report_controls_and_images_without_policy_violations(page):
    assert page.locator('meta[http-equiv="Content-Security-Policy"]').count() == 1
    page.select_option("#status-filter", "failed")
    assert visible(page) == 1
    page.click("#expand-all")
    assert page.locator("label.zoom img").evaluate("img => img.complete && img.naturalWidth > 0")
    assert page.policy_errors == []


def test_the_failed_scenario_is_listed_first_and_open_with_its_headline(page):
    assert page.locator("details.scenario[open]").count() == 1
    first = page.locator("details.scenario").first
    assert first.get_attribute("data-name") == "admin bad"
    assert first.locator(".error-line").inner_text() == "boom"


def test_copy_button_puts_the_full_error_in_the_clipboard(page):
    button = page.locator("details.scenario button.copy")
    assert button.is_visible()
    button.click()
    assert page.evaluate("navigator.clipboard.readText()") == "boom"
    assert page.locator("details.scenario").first.get_attribute("open") is not None


def test_status_filter_works_inside_an_outline_group(tmp_path):
    rows = [outline_row(1, "passed"), outline_row(2, "failed"), outline_row(3, "passed")]
    with opened(tmp_path, [feature("Login", "features/c.feature", rows)]) as tab:
        assert tab.locator("details.outline").count() == 1
        assert "3 rows · 1 failed" in tab.locator("details.outline > summary").inner_text()
        tab.select_option("#status-filter", "passed")
        assert visible(tab) == 2
        assert tab.locator("details.outline:not([hidden])").count() == 1
        assert "2 of 3 rows" in tab.locator("details.outline > summary").inner_text()
        tab.select_option("#status-filter", "")
        assert "3 rows · 1 failed" in tab.locator("details.outline > summary").inner_text()
        assert "of 3 rows" not in tab.locator("details.outline > summary").inner_text()
        tab.fill("#search", "no such scenario")
        assert visible(tab) == 0
        assert tab.locator("details.outline:not([hidden])").count() == 0
        assert tab.locator("section.feature:not([hidden])").count() == 0


def test_the_fragment_selects_the_filters_on_load(tmp_path):
    with opened(tmp_path, LOGIN_FEATURES, "#status=failed&tag=@smoke") as tab:
        assert visible(tab) == 1
        assert tab.locator("details.scenario:not([hidden])").get_attribute("data-name") == "admin bad"
        assert tab.locator("#status-filter").input_value() == "failed"
        assert tab.locator("#tag-filter").input_value() == "@smoke"


def test_changing_a_filter_updates_the_fragment_and_reset_clears_it(page):
    page.select_option("#status-filter", "passed")
    page.fill("#search", "guest")
    assert page.evaluate("location.hash") == "#search=guest&status=passed"
    page.click("#reset")
    assert page.evaluate("location.hash") == ""


def test_the_fragment_with_a_search_text_is_restored(tmp_path):
    with opened(tmp_path, LOGIN_FEATURES, "#search=other%20ok") as tab:
        assert tab.locator("#search").input_value() == "other ok"
        assert visible(tab) == 1


def test_unknown_fragment_values_are_ignored(tmp_path):
    with opened(tmp_path, LOGIN_FEATURES, "#status=nonsense&tag=@nope&other=1") as tab:
        assert visible(tab) == 4
        assert tab.locator("#status-filter").input_value() == ""


def test_a_malformed_fragment_does_not_break_the_controls(tmp_path):
    with opened(tmp_path, LOGIN_FEATURES, "#search=%E0%A4%A&status=failed") as tab:
        assert tab.locator(".toolbar").is_visible()
        assert tab.locator("#search").input_value() == ""
        assert visible(tab) == 1


def test_expand_and_collapse_all_include_outline_groups(tmp_path):
    rows = [outline_row(1, "passed"), outline_row(2, "passed")]
    with opened(tmp_path, [feature("Login", "features/c.feature", rows)]) as tab:
        assert tab.locator("details.outline[open]").count() == 0
        tab.click("#expand-all")
        assert tab.locator("details.outline[open]").count() == 1
        assert tab.locator("details.scenario[open]").count() == 2
        tab.click("#collapse-all")
        assert tab.locator("details.outline[open]").count() == 0
