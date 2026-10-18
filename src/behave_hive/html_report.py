"""Self-contained HTML report: one file, inline CSS and one inline script, no external resources (D8)."""

from __future__ import annotations

import base64
import hashlib
import re
from html import escape
from importlib.resources import files
from string import Template

from behave_hive.merge import Report, pair_backgrounds
from behave_hive.summary import STATUS_ORDER, Summary, format_summary

IMAGE_TYPE = re.compile(r"^image/[A-Za-z0-9.+-]+$")
BASE64 = re.compile(r"^[A-Za-z0-9+/=]*$")
SLOWEST = 5

REPORT_MARKER = "behave-hive-report-4f9c2e7a"


def _page() -> Template:
    return Template(files("behave_hive").joinpath("templates/report.html").read_text(encoding="utf-8"))


def _seconds(nanoseconds: int) -> str:
    return f"{nanoseconds / 1e9:.2f}s"


def _step_nanoseconds(steps: list[dict]) -> int:
    return sum(step["result"].get("duration", 0) for step in steps)


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
    pairs = pair_backgrounds(feature["elements"])
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
    pairs = [(f, b, s) for f in report.features for b, s in pair_backgrounds(f["elements"])]
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
        + "".join(_scenario(b, s) for b, s in pair_backgrounds(feature["elements"]))
        + "</section>"
        for feature in report.features
    )
    page = _page().substitute(
        marker=REPORT_MARKER,
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
