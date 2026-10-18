import base64
import hashlib
import re

from behave_hive.html_report import REPORT_MARKER, RunInfo, render
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


def scenario(
    name="S", status="passed", steps=None, source=None, line=3, tags=(), before=None, after=None, slot=None
):
    ext = {"status": status, "behave_status": status, **(slot or {})}
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
    script = page.partition("<script>")[2].partition("</script>")[0]
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"script-src 'sha256-{digest}'" in policy.group(1)
    assert "default-src 'none'" in policy.group(1)
    assert "img-src data:" in policy.group(1)
    assert "style-src 'unsafe-inline'" in policy.group(1)
    assert policy.start() < page.index("<title>")


def test_report_carries_the_generator_marker_in_the_head():
    page = html([])
    head = page[: page.index("</head>")]
    assert f'<meta name="generator" content="{REPORT_MARKER}">' in head
    assert REPORT_MARKER == "behave-hive-report-4f9c2e7a"


# --- run context ---------------------------------------------------------------------

RUN = RunInfo(
    started="2026-10-18 10:00:00", parallel=True, workers=2, scheme="scenario",
    behave_hive="0.1.0", behave="1.3.3", python="3.14.0", command="behave-hive run --parallel -w 2",
)


def run_context(page):
    section = re.search(r'<section class="run">(.*?)</section>', page, re.S).group(1)
    pairs = re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", section, re.S)
    return {key: re.sub(r"<[^>]+>", "", value) for key, value in pairs}


def html_with_run(run, features, duration=2.0):
    report = Report(features)
    return render(report, summarize(report), duration, run=run)


def four_one_second_scenarios():
    return [feature([scenario(f"S{i}", steps=[step(duration=1_000_000_000)], line=3 + i) for i in range(4)])]


def test_run_info_shows_wall_time_scenario_time_and_speedup():
    context = run_context(html_with_run(RUN, four_one_second_scenarios()))
    assert context["Wall time"] == "2.00s"
    assert context["Scenario time"] == "4.00s"
    assert context["Speedup"] == "2.0x"


def test_run_info_shows_the_run_context():
    context = run_context(html_with_run(RUN, four_one_second_scenarios()))
    assert context["Started"] == "2026-10-18 10:00:00"
    assert context["Mode"] == "parallel, 2 workers, scheme scenario"
    assert context["Versions"] == "behave-hive 0.1.0 · behave 1.3.3 · Python 3.14.0"
    assert context["Command"] == "behave-hive run --parallel -w 2"


def test_run_info_in_sequential_mode_has_no_speedup():
    sequential = RunInfo(**{**RUN.__dict__, "parallel": False, "workers": 1})
    context = run_context(html_with_run(sequential, four_one_second_scenarios(), duration=4.0))
    assert context["Mode"] == "sequential"
    assert "Speedup" not in context
    assert context["Wall time"] == "4.00s" and context["Scenario time"] == "4.00s"


def test_run_info_without_scenario_time_has_no_speedup():
    assert "Speedup" not in run_context(html_with_run(RUN, [], duration=2.0))


def test_run_info_texts_are_escaped():
    hostile = RunInfo(**{**RUN.__dict__, "command": "<script>alert(1)</script>", "started": "<b>x</b>"})
    page = html_with_run(hostile, [])
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<b>x</b>" not in page


def test_without_run_info_there_is_no_run_section():
    assert 'class="run"' not in html([])


# --- failures first --------------------------------------------------------------------


def scenario_details(page):
    return re.findall(r'<details class="scenario"[^>]*>', page)


def names_in_order(page):
    return re.findall(r'data-name="([^"]*)"', page)


def mixed_feature():
    return feature([
        scenario("a passed", line=3),
        scenario("b failed", "failed", [step(status="failed", error="boom")], line=5),
        scenario("c undefined", "undefined", [step(status="undefined")], line=7),
        scenario("d pending", "pending", [step(status="pending")], line=9),
        scenario("e passed", line=11),
        scenario("f failed", "failed", [step(status="failed", error="bang")], line=13),
        scenario("g skipped", "skipped", [step(status="skipped")], line=15),
    ])


def test_failures_first_orders_by_severity_then_by_line():
    order = names_in_order(html([mixed_feature()]))
    assert order == ["b failed", "f failed", "c undefined", "d pending", "a passed", "e passed", "g skipped"]


def test_failures_first_opens_everything_that_did_not_pass_or_skip():
    page = html([mixed_feature()])
    opened = {m for tag in scenario_details(page) for m in re.findall(r'data-name="([^"]*)"', tag) if " open" in tag}
    assert opened == {"b failed", "f failed", "c undefined", "d pending"}


def error_summary(page, name):
    block = re.search(rf'<details class="scenario"[^>]*data-name="{name}".*?</summary>', page, re.S).group(0)
    found = re.search(r'<span class="error-line">(.*?)</span>', block, re.S)
    return found.group(1) if found else None


def test_failures_first_shows_the_first_line_of_the_error_in_the_summary():
    failing = scenario("boom", "failed", [step(), step(status="failed", error="AssertionError: nope\nmore\ndetail")])
    page = html([feature([failing])])
    assert error_summary(page, "boom") == "AssertionError: nope"


def test_failures_first_summary_skips_a_generic_prefix_line():
    failing = scenario("generic", "failed", [step(status="failed", error="ASSERT FAILED:\n\nExpected 3 got 4\n")])
    assert error_summary(html([feature([failing])]), "generic") == "Expected 3 got 4"


def test_failures_first_summary_uses_a_hook_error_when_no_step_failed():
    hooked = scenario("hooked", "failed", [step()], after=hook("cleanup <broke>"))
    assert error_summary(html([feature([hooked])]), "hooked") == "cleanup &lt;broke&gt;"


def test_failures_first_summary_is_empty_without_an_error_and_for_passed_scenarios():
    page = html([feature([scenario("fine"), scenario("silent", "failed", [step(status="failed")])])])
    assert error_summary(page, "fine") is None
    assert error_summary(page, "silent") is None


def test_failures_first_copy_button_is_hidden_until_the_script_runs():
    failing = scenario("boom", "failed", [step(status="failed", error="x")])
    page = html([feature([failing])])
    assert '<button type="button" class="copy" hidden>Copy error</button>' in page
    assert page.count('class="copy"') == 1


# --- worker and batch -------------------------------------------------------------------


def test_batch_reference_shows_worker_batch_and_the_log_file():
    page = html([feature([scenario("ran", slot={"worker": 1, "batch": 2})])])
    body = re.search(r'<p class="slot">(.*?)</p>', page, re.S).group(1)
    assert re.sub(r"<[^>]+>", "", body) == "worker 1 · batch 2 · logs/batch-2.log"


def test_batch_reference_is_absent_without_worker_and_batch():
    assert 'class="slot"' not in html([feature([scenario("ran"), scenario("half", slot={"worker": 1})])])


# --- outline groups ------------------------------------------------------------------------


def outline_row(n, status="passed", outline="Login", key="f;login-l5", line=None):
    row = scenario(f"{outline} -- @1.{n} ", status, [step(status=status, error="no" if status == "failed" else None)],
                   line=line or 8 + n)
    row["id"] = f"{key};;{n}"
    return row


def test_outline_group_shows_the_outline_once_with_the_row_counts():
    rows = [outline_row(1), outline_row(2, "failed"), outline_row(3)]
    page = html([feature(rows)])
    assert page.count('<details class="outline"') == 1
    head = re.search(r'<details class="outline"[^>]*><summary>(.*?)</summary>', page, re.S).group(1)
    assert re.sub(r"<[^>]+>", "", head).split() == ["Login", "3", "rows", "·", "1", "failed"]
    assert page.count('<details class="scenario"') == 3
    assert page.index('<details class="outline"') < page.index('<details class="scenario"')


def test_outline_group_with_only_passed_rows_says_so():
    page = html([feature([outline_row(1), outline_row(2)])])
    head = re.search(r'<details class="outline"[^>]*><summary>(.*?)</summary>', page, re.S).group(1)
    assert "2 rows · all passed" in re.sub(r"<[^>]+>", "", head)


def test_outline_group_is_open_only_when_a_row_did_not_pass():
    bad = html([feature([outline_row(1, "failed")])])
    good = html([feature([outline_row(1)])])
    assert re.search(r'<details class="outline"[^>]* open>', bad)
    assert not re.search(r'<details class="outline"[^>]* open>', good)


def test_outline_group_rows_and_groups_follow_failures_first():
    rows = [
        outline_row(1, outline="Slow", key="f;slow-l5"),
        outline_row(2, "failed", outline="Slow", key="f;slow-l5"),
        outline_row(1, outline="Fast", key="f;fast-l20", line=21),
    ]
    order = names_in_order(html([feature([*rows, scenario("plain", line=30)])]))
    assert order == ["slow -- @1.2 ", "slow -- @1.1 ", "fast -- @1.1 ", "plain"]


def test_outline_group_name_is_escaped_and_plain_scenarios_stay_ungrouped():
    page = html([feature([outline_row(1, outline="<b>x</b>"), scenario("solo", line=30)])])
    assert "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt;" in page
    assert page.count('<details class="outline"') == 1 and page.count('<details class="scenario"') == 2


def test_failures_first_whitespace_only_error_has_the_button_but_no_headline():
    blank = scenario("blank", "failed", [step(status="failed", error=" \n  ")])
    page = html([feature([blank])])
    assert error_summary(page, "blank") is None
    assert 'class="copy"' in page
