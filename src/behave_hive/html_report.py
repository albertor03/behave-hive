"""Self-contained HTML report: one file, inline CSS and one inline script, no external resources (D8)."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from html import escape
from importlib.resources import files
from string import Template

from behave_hive.merge import Report, pair_backgrounds
from behave_hive.summary import STATUS_ORDER, Summary, format_summary

IMAGE_TYPE = re.compile(r"^image/[A-Za-z0-9.+-]+$")
BASE64 = re.compile(r"^[A-Za-z0-9+/=]*$")
SLOWEST = 5
SEVERITY = ("failed", "undefined", "pending")

REPORT_MARKER = "behave-hive-report-4f9c2e7a"


@dataclass(frozen=True)
class RunInfo:
    """What the page says about how the run was made; `render`'s `duration` is its wall time."""

    started: str
    parallel: bool
    workers: int
    scheme: str
    behave_hive: str
    behave: str
    python: str
    command: str


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


def _error_text(steps: list[dict], scenario: dict) -> str:
    """The first step error, else the first hook error, else an empty string."""
    hooks = [*scenario.get("before", []), *scenario.get("after", [])]
    for item in (*steps, *hooks):
        message = item["result"].get("error_message")
        if message:
            return message
    return ""


def _error_line(error: str) -> str:
    """First non-empty line; the last one when the first is only a prefix such as `ASSERT FAILED:`."""
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1] if lines[0].endswith(":") and len(lines) > 1 else lines[0]


def _slot_line(ext: dict) -> str:
    if "worker" not in ext or "batch" not in ext:
        return ""
    return (
        f'<p class="slot">worker {int(ext["worker"])} · batch {int(ext["batch"])} · '
        f'<span class="muted">logs/batch-{int(ext["batch"])}.log</span></p>'
    )


def _failure_summary(error: str) -> str:
    """The error's headline and the copy button (shown by the script); empty without an error."""
    if not error:
        return ""
    line = _error_line(error)
    headline = f'<span class="error-line">{escape(line)}</span>' if line else ""
    return headline + '<button type="button" class="copy" hidden>Copy error</button>'


def _outline_key(scenario: dict) -> str | None:
    """The id of the outline a row came from (`<feature>;<outline>-l<line>`), or None for a plain scenario."""
    head, separator, _ = scenario["id"].partition(";;")
    return head if separator else None


def _entries(pairs: list[tuple[dict | None, dict]]) -> list[list[tuple[dict | None, dict]]]:
    """Plain scenarios alone and outline rows together, the worst first (stable on line order)."""
    entries: dict[object, list[tuple[dict | None, dict]]] = {}
    for index, pair in enumerate(pairs):
        entries.setdefault(_outline_key(pair[1]) or index, []).append(pair)
    return sorted(
        ([*sorted(rows, key=_severity)] for rows in entries.values()),
        key=lambda rows: _severity(rows[0]),
    )


def _outline_group(rows: list[tuple[dict | None, dict]]) -> str:
    statuses = [scenario["x-behave-hive"]["status"] for _, scenario in rows]
    problems = " · ".join(f"{statuses.count(st)} {st}" for st in STATUS_ORDER if st != "passed" and st in statuses)
    name = rows[0][1]["name"].partition(" -- @")[0]
    opened = " open" if any(st in SEVERITY for st in statuses) else ""
    return (
        f'<details class="outline"{opened}><summary><span>{escape(name)}</span> '
        f'<span class="muted"><span class="count" data-total="{len(rows)}">{len(rows)} rows</span>'
        f' · {problems or "all passed"}</span></summary>'
        + "".join(_scenario(b, s) for b, s in rows)
        + "</details>"
    )


def _entry(rows: list[tuple[dict | None, dict]]) -> str:
    if _outline_key(rows[0][1]) is None:
        return _scenario(*rows[0])
    return _outline_group(rows)


def _severity(pair: tuple[dict | None, dict]) -> int:
    status = pair[1]["x-behave-hive"]["status"]
    return SEVERITY.index(status) if status in SEVERITY else len(SEVERITY)


def _scenario(background: dict | None, scenario: dict) -> str:
    ext = scenario["x-behave-hive"]
    status = escape(ext["status"])
    tags = [t["name"] for t in scenario.get("tags", [])]
    steps = [*(background["steps"] if background else []), *scenario["steps"]]
    chips = "".join(f'<span class="chip">{escape(t)}</span>' for t in tags)
    failure = _failure_summary(_error_text(steps, scenario))
    opened = " open" if ext["status"] in SEVERITY else ""
    source = ""
    if ext.get("source"):
        source = f'<span class="source">{escape(ext["source"]["data_path"])}:{ext["source"]["data_row"]}</span>'
    return (
        f'<details class="scenario" data-status="{status}" data-tags="{escape(" ".join(tags))}" '
        f'data-name="{escape(scenario["name"].lower())}"{opened}>'
        f'<summary><span class="status {status}">{status}</span><span>{escape(scenario["name"])}</span>'
        f"{chips}{source}{failure}"
        f'<span class="duration">{_seconds(_step_nanoseconds(steps))}</span></summary>'
        f'{_slot_line(ext)}{_hooks(scenario, "before", "Before")}'
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


def _run_info(run: RunInfo | None, wall_seconds: float, scenario_nanoseconds: int) -> str:
    if run is None:
        return ""
    scenario_seconds = scenario_nanoseconds / 1e9
    rows = [
        ("Started", run.started),
        ("Mode", f"parallel, {run.workers} workers, scheme {run.scheme}" if run.parallel else "sequential"),
        ("Versions", f"behave-hive {run.behave_hive} · behave {run.behave} · Python {run.python}"),
        ("Command", run.command),
        ("Wall time", f"{wall_seconds:.2f}s"),
        ("Scenario time", f"{scenario_seconds:.2f}s"),
    ]
    if run.parallel and scenario_seconds and wall_seconds:
        rows.append(("Speedup", f"{scenario_seconds / wall_seconds:.1f}x"))
    body = "".join(f"<dt>{label}</dt><dd>{escape(value)}</dd>" for label, value in rows)
    return f'<section class="run"><dl>{body}</dl></section>'


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
    report: Report,
    summary: Summary,
    duration: float,
    *,
    report_name: str = "behave-hive report",
    run: RunInfo | None = None,
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
        + "".join(_entry(rows) for rows in _entries(pair_backgrounds(feature["elements"])))
        + "</section>"
        for feature in report.features
    )
    page = _page().substitute(
        marker=REPORT_MARKER,
        report_name=escape(report_name),
        totals=escape(format_summary(summary, duration)),
        statusbar=statusbar,
        run_info=_run_info(run, duration, sum(s["nanoseconds"] for _, s in stats)),
        metrics=_metrics(summary, stats, pairs),
        feature_rows="\n".join(_feature_row(f, s) for f, s in stats),
        totals_row=totals_row,
        status_options="".join(f'<option value="{st}">{st}</option>' for st in statuses_present),
        tag_options="".join(f'<option value="{escape(t)}">{escape(t)}</option>' for t in tags),
        features=sections,
    )
    script = page.partition("<script>")[2].partition("</script>")[0]
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    policy = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{digest}'"
    return page.replace("<!--CSP-->", f'<meta http-equiv="Content-Security-Policy" content="{policy}">', 1)
