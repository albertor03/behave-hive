"""Self-contained HTML report: one file, inline CSS and one inline script, no external resources (D8)."""

from __future__ import annotations

import base64
import hashlib
import re
from html import escape
from string import Template

from behave_hive.merge import Report
from behave_hive.summary import STATUS_ORDER, Summary, format_summary

IMAGE_TYPE = re.compile(r"^image/[A-Za-z0-9.+-]+$")
BASE64 = re.compile(r"^[A-Za-z0-9+/=]*$")
SLOWEST = 5

PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!--CSP-->
<title>$report_name</title>
<style>
:root {
  --bg: #ffffff; --fg: #1d2330; --muted: #5d6677; --border: #d9dde6; --card: #f6f7fa; --accent: #3a5bd9;
  --passed: #1a7f37; --failed: #cf222e; --undefined: #9a6700; --pending: #8250df; --skipped: #6e7781;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151c; --fg: #e6e9f0; --muted: #98a1b3; --border: #2a3040; --card: #1a1f2a; --accent: #7d96ff;
    --passed: #3fb950; --failed: #ff7b72; --undefined: #d29922; --pending: #bc8cff; --skipped: #8b949e;
  }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.05rem; margin: 0 0 8px; }
h2 small { color: var(--muted); font-weight: normal; margin-left: 8px; }
.totals { color: var(--muted); margin: 0 0 12px; }
.statusbar { display: flex; height: 8px; border-radius: 4px; overflow: hidden;
  background: var(--border); margin: 0 0 24px; }
.statusbar span { display: block; height: 100%; }
.bg-passed { background: var(--passed); } .bg-failed { background: var(--failed); }
.bg-undefined { background: var(--undefined); } .bg-pending { background: var(--pending); }
.bg-skipped { background: var(--skipped); }
.passed { color: var(--passed); } .failed { color: var(--failed); } .undefined { color: var(--undefined); }
.pending { color: var(--pending); } .skipped { color: var(--skipped); }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin: 0 0 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; }
.card h3 { margin: 0 0 8px; font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.donut-wrap { display: flex; gap: 16px; align-items: center; }
.donut { width: 96px; height: 96px; border-radius: 50%; flex: none; position: relative; }
.donut::after { content: ""; position: absolute; inset: 22px; border-radius: 50%; background: var(--card); }
.legend { list-style: none; margin: 0; padding: 0; font-size: .9rem; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
.bars { list-style: none; margin: 0; padding: 0; font-size: .85rem; }
.bars li { margin: 6px 0; }
.bars .track { display: block; height: 6px; background: var(--border); border-radius: 3px; margin-top: 2px; }
.bars .track span { display: block; height: 100%; background: var(--accent); border-radius: 3px; }
.slowest { margin: 0; padding-left: 20px; font-size: .85rem; }
.slowest li { margin: 4px 0; }
.slowest small, .muted { color: var(--muted); }
table.features { width: 100%; border-collapse: collapse; margin: 0 0 24px; font-size: .9rem; }
table.features th, table.features td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
table.features thead th { color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase; }
table.features tr.totals-row th, table.features tr.totals-row td {
  border-top: 2px solid var(--border); font-weight: 600; }
.bar { display: inline-block; vertical-align: middle; width: 90px; height: 8px; background: var(--border);
  border-radius: 4px; overflow: hidden; margin-right: 8px; }
.bar span { display: block; height: 100%; background: var(--passed); }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 0 0 12px; }
.toolbar[hidden] { display: none; }
.toolbar input, .toolbar select, .toolbar button { font: inherit; padding: 6px 10px; color: var(--fg);
  background: var(--card); border: 1px solid var(--border); border-radius: 6px; }
.toolbar input { min-width: 220px; flex: 1; }
.toolbar button { cursor: pointer; }
.note { color: var(--muted); font-size: .9rem; }
section.feature { margin: 0 0 24px; }
section.feature[hidden], details.scenario[hidden] { display: none; }
details.scenario { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
  margin: 6px 0; padding: 6px 12px; }
details.scenario > summary { cursor: pointer; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.status { font-weight: 600; text-transform: uppercase; font-size: .72rem; letter-spacing: .03em; }
.chip { font-size: .75rem; padding: 0 6px; border: 1px solid var(--border); border-radius: 10px; color: var(--muted); }
.source, .duration { color: var(--muted); font-size: .85rem; }
.duration { margin-left: auto; }
ol.steps { margin: 8px 0 4px; padding-left: 22px; }
ol.steps li { margin: 4px 0; }
pre { margin: 4px 0 8px; padding: 8px; background: var(--bg); border: 1px solid var(--border);
  border-radius: 4px; overflow-x: auto; white-space: pre-wrap; font-size: .8rem; }
table.rows { border-collapse: collapse; margin: 4px 0; font-size: .85rem; }
table.rows th, table.rows td { border: 1px solid var(--border); padding: 2px 8px; text-align: left; }
.hook { margin: 6px 0; }
label.zoom { display: block; margin: 6px 0; cursor: zoom-in; }
label.zoom input { display: none; }
label.zoom img { max-width: 320px; max-height: 200px; border: 1px solid var(--border); border-radius: 4px; }
label.zoom input:checked + img { max-width: 100%; max-height: none; cursor: zoom-out; }
</style>
</head>
<body>
<main>
<h1>$report_name</h1>
<p class="totals">$totals</p>
<div class="statusbar">$statusbar</div>
<section class="metrics">
$metrics
</section>
<table class="features">
<thead><tr><th>Feature</th><th>Total</th><th>Executed</th><th>Pass</th><th>Duration</th></tr></thead>
<tbody>
$feature_rows
$totals_row
</tbody>
</table>
<div class="toolbar" hidden>
<input id="search" type="search" placeholder="Search scenario name..." aria-label="Search scenarios">
<select id="status-filter" aria-label="Filter by status"><option value="">All statuses</option>$status_options</select>
<select id="tag-filter" aria-label="Filter by tag"><option value="">All tags</option>$tag_options</select>
<button type="button" id="reset">Reset</button>
<button type="button" id="expand-all">Expand all</button>
<button type="button" id="collapse-all">Collapse all</button>
<span class="note" id="shown"></span>
</div>
<noscript><p class="note">Filters need JavaScript; every scenario is listed below and can be expanded.</p></noscript>
$features
</main>
<script>
(function () {
  var bar = document.querySelector(".toolbar");
  if (!bar) { return; }
  bar.hidden = false;
  var search = document.getElementById("search");
  var status = document.getElementById("status-filter");
  var tag = document.getElementById("tag-filter");
  var shown = document.getElementById("shown");
  var scenarios = Array.prototype.slice.call(document.querySelectorAll("details.scenario"));
  var features = Array.prototype.slice.call(document.querySelectorAll("section.feature"));
  function apply() {
    var text = search.value.trim().toLowerCase();
    var visible = 0;
    scenarios.forEach(function (el) {
      var ok = (!text || el.getAttribute("data-name").indexOf(text) !== -1) &&
        (!status.value || el.getAttribute("data-status") === status.value) &&
        (!tag.value || (" " + el.getAttribute("data-tags") + " ").indexOf(" " + tag.value + " ") !== -1);
      el.hidden = !ok;
      if (ok) { visible += 1; }
    });
    features.forEach(function (section) {
      section.hidden = !section.querySelector("details.scenario:not([hidden])");
    });
    shown.textContent = "Showing " + visible + " of " + scenarios.length;
  }
  function setOpen(open) {
    scenarios.forEach(function (el) { if (!el.hidden) { el.open = open; } });
  }
  search.addEventListener("input", apply);
  status.addEventListener("change", apply);
  tag.addEventListener("change", apply);
  document.getElementById("reset").addEventListener("click", function () {
    search.value = ""; status.value = ""; tag.value = ""; apply();
  });
  document.getElementById("expand-all").addEventListener("click", function () { setOpen(true); });
  document.getElementById("collapse-all").addEventListener("click", function () { setOpen(false); });
  apply();
})();
</script>
</body>
</html>
"""
)


def _seconds(nanoseconds: int) -> str:
    return f"{nanoseconds / 1e9:.2f}s"


def _step_nanoseconds(steps: list[dict]) -> int:
    return sum(step["result"].get("duration", 0) for step in steps)


def _pairs(elements: list[dict]) -> list[tuple[dict | None, dict]]:
    pairs, background = [], None
    for element in elements:
        if element["type"] == "background":
            background = element
        else:
            pairs.append((background, element))
            background = None
    return pairs


def _image(embedding: dict) -> str:
    mime, data = embedding.get("mime_type", ""), embedding.get("data", "")
    if not (IMAGE_TYPE.match(mime) and BASE64.match(data)):
        return ""
    return (
        f'<label class="zoom"><input type="checkbox">'
        f'<img src="data:{mime};base64,{data}" alt="evidence"></label>'
    )


def _step(step: dict) -> str:
    result = step["result"]
    status = escape(result["status"])
    parts = [
        f'<li><span class="status {status}">{status}</span> '
        f'{escape(step["keyword"])}{escape(step["name"])} '
        f'<span class="duration">{_seconds(result.get("duration", 0))}</span>'
    ]
    if step.get("rows"):
        header, *body = step["rows"]
        head = "".join(f"<th>{escape(c)}</th>" for c in header["cells"])
        lines = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r["cells"]) + "</tr>" for r in body)
        parts.append(f'<table class="rows"><tr>{head}</tr>{lines}</table>')
    if result.get("error_message"):
        parts.append(f'<pre>{escape(result["error_message"])}</pre>')
    parts.extend(_image(e) for e in step.get("embeddings", []))
    return "".join(parts) + "</li>"


def _hooks(element: dict, key: str, label: str) -> str:
    out = []
    for hook in element.get(key, []):
        result = hook["result"]
        location = escape(hook.get("match", {}).get("location", ""))
        out.append(
            f'<div class="hook"><span class="status failed">{escape(result["status"])}</span> '
            f'{label} hook <span class="muted">{location}</span>'
            f'<pre>{escape(result.get("error_message", ""))}</pre></div>'
        )
    return "".join(out)


def _scenario_nanoseconds(background: dict | None, scenario: dict) -> int:
    return _step_nanoseconds([*(background["steps"] if background else []), *scenario["steps"]])


def _scenario(background: dict | None, scenario: dict) -> str:
    ext = scenario["x-behave-hive"]
    status = escape(ext["status"])
    tags = [t["name"] for t in scenario.get("tags", [])]
    steps = [*(background["steps"] if background else []), *scenario["steps"]]
    chips = "".join(f'<span class="chip">{escape(t)}</span>' for t in tags)
    source = ""
    if ext.get("source"):
        source = f'<span class="source">{escape(ext["source"]["csv_path"])}:{ext["source"]["csv_row"]}</span>'
    return (
        f'<details class="scenario" data-status="{status}" data-tags="{escape(" ".join(tags))}" '
        f'data-name="{escape(scenario["name"].lower())}">'
        f'<summary><span class="status {status}">{status}</span><span>{escape(scenario["name"])}</span>'
        f"{chips}{source}"
        f'<span class="duration">{_seconds(_step_nanoseconds(steps))}</span></summary>'
        f'{_hooks(scenario, "before", "Before")}'
        f'<ol class="steps">{"".join(_step(s) for s in steps)}</ol>'
        f'{_hooks(scenario, "after", "After")}</details>'
    )


def _stats(feature: dict) -> dict:
    pairs = _pairs(feature["elements"])
    statuses = [scenario["x-behave-hive"]["status"] for _, scenario in pairs]
    return {
        "total": len(pairs),
        "executed": sum(1 for s in statuses if s != "skipped"),
        "passed": sum(1 for s in statuses if s == "passed"),
        "nanoseconds": sum(_scenario_nanoseconds(b, s) for b, s in pairs),
    }


def _pass_cell(passed: int, executed: int) -> str:
    if not executed:
        return '<span class="muted">-</span>'
    percent = round(passed / executed * 100)
    return f'<span class="bar"><span style="width:{percent}%"></span></span>{percent}%'


def _feature_row(feature: dict, stats: dict) -> str:
    return (
        f'<tr class="feature-row"><th scope="row">{escape(feature["name"])}</th>'
        f'<td>{stats["total"]}</td><td>{stats["executed"]}</td>'
        f'<td>{_pass_cell(stats["passed"], stats["executed"])}</td>'
        f'<td>{_seconds(stats["nanoseconds"])}</td></tr>'
    )


def _donut(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if not total:
        return "background: var(--border)"
    stops, start = [], 0.0
    for status in STATUS_ORDER:
        if counts.get(status):
            end = start + counts[status] / total * 100
            stops.append(f"var(--{status}) {start:.2f}% {end:.2f}%")
            start = end
    return f"background: conic-gradient({', '.join(stops)})"


def _metrics(summary: Summary, stats: list[tuple[dict, dict]], pairs: list[tuple[dict, dict | None, dict]]) -> str:
    legend = "".join(
        f'<li><span class="dot bg-{status}"></span><b>{summary.scenarios[status]}</b> {status}</li>'
        for status in STATUS_ORDER
        if summary.scenarios.get(status)
    ) or '<li class="muted">no scenarios</li>'
    longest = max((s["nanoseconds"] for _, s in stats), default=0) or 1
    bars = "".join(
        f'<li>{escape(f["name"])} <span class="muted">{_seconds(s["nanoseconds"])}</span>'
        f'<span class="track"><span style="width:{s["nanoseconds"] / longest * 100:.1f}%"></span></span></li>'
        for f, s in stats
    ) or '<li class="muted">no features</li>'
    slow = sorted(pairs, key=lambda item: _scenario_nanoseconds(item[1], item[2]), reverse=True)[:SLOWEST]
    slowest = "".join(
        f'<li>{escape(scenario["name"])} <small>{escape(feature["name"])}</small> '
        f'<span class="duration">{_seconds(_scenario_nanoseconds(background, scenario))}</span></li>'
        for feature, background, scenario in slow
    )
    return (
        f'<div class="card"><h3>Status</h3><div class="donut-wrap">'
        f'<div class="donut" style="{_donut(summary.scenarios)}"></div><ul class="legend">{legend}</ul></div></div>\n'
        f'<div class="card"><h3>Duration by feature</h3><ul class="bars">{bars}</ul></div>\n'
        f'<div class="card"><h3>Slowest scenarios</h3><ol class="slowest">{slowest}</ol></div>'
    )


def render(
    report: Report, summary: Summary, duration: float, *, report_name: str = "behave-hive report"
) -> str:
    """The report page for `report`; every text is escaped and images are validated."""
    stats = [(feature, _stats(feature)) for feature in report.features]
    pairs = [(f, b, s) for f in report.features for b, s in _pairs(f["elements"])]
    statuses_present = [st for st in STATUS_ORDER if summary.scenarios.get(st)]
    tags = sorted({t["name"] for _, _, s in pairs for t in s.get("tags", [])})
    total = sum(s["total"] for _, s in stats)
    executed = sum(s["executed"] for _, s in stats)
    passed = sum(s["passed"] for _, s in stats)
    totals_row = (
        f'<tr class="totals-row"><th scope="row">Totals</th><td>{total}</td><td>{executed}</td>'
        f'<td>{_pass_cell(passed, executed)}</td>'
        f'<td>{_seconds(sum(s["nanoseconds"] for _, s in stats))}</td></tr>'
    )
    statusbar = "".join(
        f'<span class="bg-{st}" style="width:{summary.scenarios[st] / total * 100:.2f}%"></span>'
        for st in statuses_present
    ) if total else ""
    sections = "\n".join(
        f'<section class="feature"><h2>{escape(feature["name"])}<small>{escape(feature["uri"])}</small></h2>'
        + "".join(_scenario(b, s) for b, s in _pairs(feature["elements"]))
        + "</section>"
        for feature in report.features
    )
    page = PAGE.substitute(
        report_name=escape(report_name),
        totals=escape(format_summary(summary, duration)),
        statusbar=statusbar,
        metrics=_metrics(summary, stats, pairs),
        feature_rows="\n".join(_feature_row(f, s) for f, s in stats),
        totals_row=totals_row,
        status_options="".join(f'<option value="{st}">{st}</option>' for st in statuses_present),
        tag_options="".join(f'<option value="{escape(t)}">{escape(t)}</option>' for t in tags),
        features=sections,
    )
    script = re.search(r"<script>(.*?)</script>", page, re.S)[1]
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    policy = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{digest}'"
    return page.replace("<!--CSP-->", f'<meta http-equiv="Content-Security-Policy" content="{policy}">', 1)
