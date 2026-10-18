import base64
import hashlib
import re

from behave_hive.html_report import render
from behave_hive.merge import Report
from behave_hive.summary import summarize

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def step(name="step", status="passed", duration=250_000_000, error=None, embeddings=None, rows=None):
    result = {"status": status, "duration": duration}
    if error:
        result["error_message"] = error
    data = {"keyword": "Given ", "name": name, "line": 3, "result": result}
    if embeddings:
        data["embeddings"] = embeddings
    if rows:
        data["rows"] = rows
    return data


def scenario(name="S", status="passed", steps=None, source=None, line=3, tags=(), before=None, after=None):
    ext = {"status": status, "behave_status": status}
    if source:
        ext["source"] = source
    element = {
        "id": f"f;{name}-l{line}", "keyword": "Scenario", "name": name, "description": "", "line": line,
        "type": "scenario", "tags": [{"name": t, "line": 1} for t in tags], "steps": steps or [step()],
        "x-behave-hive": ext,
    }
    if before:
        element["before"] = before
    if after:
        element["after"] = after
    return element


def hook(message):
    return [{
        "match": {"location": "environment.py"},
        "result": {"status": "failed", "duration": 0, "error_message": message},
    }]


def feature(elements, name="Login", uri="features/login.feature"):
    return {
        "uri": uri, "id": "f", "keyword": "Feature", "name": name,
        "description": "", "line": 1, "tags": [], "elements": elements,
    }


def html(features, duration=8.4):
    report = Report(features)
    return render(report, summarize(report), duration)


# --- totals, table and metrics -----------------------------------------------------


def test_shows_totals_and_duration():
    page = html([feature([scenario("A"), scenario("B", "failed", [step(status="failed", error="boom")])])])
    assert "1 feature · 2 scenarios (1 passed, 1 failed) · 2 steps (1 passed, 1 failed) · 8.4s" in page


def test_feature_table_has_total_executed_pass_percentage_and_duration():
    page = html([feature([scenario("A"), scenario("B", "failed"), scenario("C", "skipped")])])
    row = re.search(r'<tr class="feature-row"[^>]*>(.*?)</tr>', page, re.S).group(1)
    cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
    assert cells[0] == "Login"
    assert cells[1] == "3"  # total
    assert cells[2] == "2"  # executed: skipped scenarios do not count
    assert "50%" in cells[3]
    assert "s" in cells[4]


def test_feature_table_has_a_totals_row():
    page = html([
        feature([scenario("A")], name="One"),
        feature([scenario("B", "failed")], name="Two", uri="features/b.feature"),
    ])
    totals = re.search(r'<tr class="totals-row"[^>]*>(.*?)</tr>', page, re.S).group(1)
    text = re.sub(r"<[^>]+>", " ", totals)
    assert "Totals" in text and "2" in text and "50%" in text


def test_metrics_status_breakdown_lists_each_status_with_its_count():
    page = html([feature([scenario("A"), scenario("B"), scenario("C", "failed")])])
    metrics = re.search(r'<section class="metrics".*?</section>', page, re.S).group(0)
    assert "conic-gradient" in metrics
    assert re.search(r"2\s*(<[^>]+>\s*)*passed", metrics)
    assert re.search(r"1\s*(<[^>]+>\s*)*failed", metrics)


def test_metrics_duration_per_feature():
    page = html([
        feature([scenario("A", steps=[step(duration=2_000_000_000)])], name="Slow"),
        feature([scenario("B", steps=[step(duration=500_000_000)])], name="Fast", uri="features/b.feature"),
    ])
    metrics = re.search(r'<section class="metrics".*?</section>', page, re.S).group(0)
    assert "Slow" in metrics and "Fast" in metrics
    assert "2.00s" in metrics and "0.50s" in metrics


def test_metrics_list_the_five_slowest_scenarios_slowest_first():
    elements = [scenario(f"S{i}", steps=[step(duration=i * 1_000_000_000)], line=i + 2) for i in range(1, 8)]
    page = html([feature(elements)])
    slowest = re.search(r'<ol class="slowest">(.*?)</ol>', page, re.S).group(1)
    names = re.findall(r"S\d", re.sub(r"<[^>]+>", " ", slowest))
    assert names == ["S7", "S6", "S5", "S4", "S3"]


# --- scenarios -------------------------------------------------------------------------


def test_shows_features_scenarios_steps_and_error_message():
    page = html([feature([scenario("A", "failed", [step("open page", "failed", 1_500_000_000, "boom happened")])])])
    for text in ("Login", "features/login.feature", "A", "open page", "boom happened", "1.50s", "failed"):
        assert text in page


def test_scenario_carries_filter_attributes_and_tag_chips():
    page = html([feature([scenario("Admin login", "failed", tags=("@smoke", "@web"))])])
    details = re.search(r"<details[^>]*>", page).group(0)
    assert 'data-status="failed"' in details
    assert 'data-tags="@smoke @web"' in details
    assert 'data-name="admin login"' in details
    assert page.count("@smoke") >= 2  # chip and filter option


def test_shows_the_csv_source_next_to_the_scenario():
    source = {"csv_path": "features/data/login.csv", "csv_row": 3}
    assert "features/data/login.csv:3" in html([feature([scenario("A", source=source)])])


def test_scenario_without_source_shows_no_csv_reference():
    assert ".csv" not in html([feature([scenario("A")])])


def test_step_table_rows_are_shown():
    page = html([feature([scenario("A", steps=[step(rows=[{"cells": ["a", "b"]}, {"cells": ["1", "2"]}])])])])
    assert "<table" in page and "<td>1</td>" in page


def test_hook_errors_are_shown():
    page = html([feature([scenario("A", "failed", before=hook("before boom"), after=hook("after boom"))])])
    assert "before boom" in page and "after boom" in page


# --- evidence ---------------------------------------------------------------------------


def test_image_embeddings_are_shown_inline_in_the_step():
    page = html([feature([scenario("A", "failed", [
        step("shot", "failed", error="x", embeddings=[{"mime_type": "image/png", "data": PNG}]),
    ])])])
    assert f'src="data:image/png;base64,{PNG}"' in page
    assert 'class="zoom"' in page


def test_non_image_embeddings_are_not_rendered_as_images():
    page = html([feature([scenario("A", steps=[step(embeddings=[{"mime_type": "text/plain", "data": "aGk="}])])])])
    assert "data:text/plain" not in page


def test_hostile_embedding_types_and_data_are_ignored():
    hostile = [
        {"mime_type": 'image/png" onerror="x', "data": PNG},
        {"mime_type": "image/png", "data": 'AAAA" onerror="x'},
    ]
    page = html([feature([scenario("A", steps=[step(embeddings=hostile)])])])
    assert "onerror" not in page and "<img" not in page


# --- toolbar and script ------------------------------------------------------------------


def test_toolbar_has_search_status_and_tag_filters_and_buttons():
    page = html([feature([scenario("A", tags=("@smoke",)), scenario("B", "failed", tags=("@web",))])])
    toolbar = re.search(r'<div class="toolbar".*?</div>', page, re.S).group(0)
    assert 'type="search"' in toolbar
    assert '<select id="status-filter"' in toolbar and 'value="failed"' in toolbar
    assert '<select id="tag-filter"' in toolbar and 'value="@smoke"' in toolbar and 'value="@web"' in toolbar
    for label in ("Reset", "Expand all", "Collapse all"):
        assert label in toolbar


def test_the_only_script_is_inline_and_a_noscript_fallback_exists():
    page = html([feature([scenario("A")])])
    assert page.lower().count("<script") == 1
    assert re.search(r"<script(?![^>]*\bsrc=)", page)
    assert "<noscript>" in page


def test_is_self_contained_without_external_urls():
    page = html([feature([scenario("A", steps=[step(embeddings=[{"mime_type": "image/png", "data": PNG}])])])])
    assert not re.search(r"https?://", page)
    assert "<link" not in page.lower()
    assert " src=\"http" not in page


def test_supports_dark_mode():
    assert "prefers-color-scheme: dark" in html([feature([scenario("A")])])


def test_names_are_escaped_and_cannot_inject_scripts():
    page = html([feature(
        [scenario(
            "<script>alert(1)</script>", tags=("@<b>",),
            steps=[step("<img src=x onerror=1>", "failed", error="<b>x</b>")],
        )],
        name="<script>f</script>",
    )])
    assert "<script>alert" not in page and "<script>f" not in page
    assert page.lower().count("<script") == 1
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=1&gt;" in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_is_a_complete_document_with_one_details_per_scenario():
    page = html([feature([scenario("A"), scenario("B")])])
    assert page.lstrip().lower().startswith("<!doctype html>")
    assert page.count("<details") == 2
    assert '<meta charset="utf-8">' in page


def test_empty_report_renders():
    page = html([])
    assert "0 scenarios" in page and "<table" in page


def test_background_steps_are_paired_with_only_the_following_scenario():
    background = {
        "type": "background", "keyword": "Background", "name": "Shared", "line": 2,
        "steps": [step("shared setup", duration=1_000_000_000)],
    }
    page = html([feature([
        background, scenario("With setup", steps=[step("first action", duration=2_000_000_000)]),
        scenario("Without setup", steps=[step("second action", duration=500_000_000)]),
    ])])
    first, second = re.findall(r'<details class="scenario".*?</details>', page, re.S)
    assert first.index("shared setup") < first.index("first action")
    assert "3.00s" in first
    assert "shared setup" not in second
    assert "0.50s" in second
    assert "2 scenarios" in page and "3 steps" in page


def test_report_name_sets_both_document_title_and_heading():
    report = Report([])
    page = render(report, summarize(report), 0.0, report_name="Portal QA")
    assert "<title>Portal QA</title>" in page
    assert "<h1>Portal QA</h1>" in page


def test_report_name_is_escaped_in_title_and_heading():
    report = Report([])
    page = render(report, summarize(report), 0.0, report_name='<script>alert("x")</script>')
    assert '<script>alert("x")</script>' not in page
    assert "<title>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</title>" in page
    assert "<h1>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</h1>" in page


def test_report_name_direct_render_default_is_preserved():
    page = html([])
    assert "<title>behave-hive report</title>" in page
    assert "<h1>behave-hive report</h1>" in page


def test_csp_hash_matches_the_exact_emitted_script():
    page = html([feature([scenario("<script>hostile</script>")])])
    policy = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', page)
    assert policy
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in policy.group(1)
    assert "default-src 'none'" in policy.group(1)
    assert "img-src data:" in policy.group(1)
    assert "style-src 'unsafe-inline'" in policy.group(1)
    assert policy.start() < page.index("<title>")
