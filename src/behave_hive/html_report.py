"""Self-contained HTML report: no JavaScript, no external resources (D8)."""

from __future__ import annotations

from html import escape
from string import Template

from behave_hive.merge import Report
from behave_hive.summary import Summary, format_summary

PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>behave-hive report</title>
<style>
:root {
  --bg: #ffffff; --fg: #1d2330; --muted: #5d6677; --border: #d9dde6; --card: #f6f7fa;
  --passed: #1a7f37; --failed: #cf222e; --undefined: #9a6700; --pending: #8250df; --skipped: #6e7781;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151c; --fg: #e6e9f0; --muted: #98a1b3; --border: #2a3040; --card: #1a1f2a;
    --passed: #3fb950; --failed: #ff7b72; --undefined: #d29922; --pending: #bc8cff; --skipped: #8b949e;
  }
}
body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 4px; }
.totals { color: var(--muted); margin: 0 0 24px; }
section { margin: 0 0 24px; }
h2 { font-size: 1.05rem; margin: 0 0 8px; }
h2 small { color: var(--muted); font-weight: normal; margin-left: 8px; }
details { background: var(--card); border: 1px solid var(--border); border-radius: 6px; margin: 6px 0; padding: 6px 12px; }
summary { cursor: pointer; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.status { font-weight: 600; text-transform: uppercase; font-size: .72rem; letter-spacing: .03em; }
.passed { color: var(--passed); } .failed { color: var(--failed); } .undefined { color: var(--undefined); }
.pending { color: var(--pending); } .skipped { color: var(--skipped); }
.source, .duration { color: var(--muted); font-size: .85rem; }
ol { margin: 8px 0 4px; padding-left: 22px; }
li { margin: 2px 0; }
pre { margin: 4px 0 8px; padding: 8px; background: var(--bg); border: 1px solid var(--border);
  border-radius: 4px; overflow-x: auto; white-space: pre-wrap; font-size: .8rem; }
</style>
</head>
<body>
<main>
<h1>behave-hive report</h1>
<p class="totals">$totals</p>
$features
</main>
</body>
</html>
"""
)


def _duration(nanoseconds: int) -> str:
    return f"{nanoseconds / 1e9:.2f}s"


def _step(step: dict) -> str:
    result = step["result"]
    status = escape(result["status"])
    text = (
        f'<li><span class="status {status}">{status}</span> '
        f'{escape(step["keyword"])}{escape(step["name"])} '
        f'<span class="duration">{_duration(result.get("duration", 0))}</span>'
    )
    if result.get("error_message"):
        text += f'<pre>{escape(result["error_message"])}</pre>'
    return text + "</li>"


def _scenario(scenario: dict, background: dict | None) -> str:
    ext = scenario["x-behave-hive"]
    status = escape(ext["status"])
    steps = [*(background["steps"] if background else []), *scenario["steps"]]
    duration = sum(s["result"].get("duration", 0) for s in steps)
    source = ""
    if ext.get("source"):
        source = f' <span class="source">{escape(ext["source"]["csv_path"])}:{ext["source"]["csv_row"]}</span>'
    return (
        f'<details><summary><span class="status {status}">{status}</span> '
        f'<span>{escape(scenario["name"])}</span>{source} '
        f'<span class="duration">{_duration(duration)}</span></summary>'
        f'<ol>{"".join(_step(s) for s in steps)}</ol></details>'
    )


def _feature(feature: dict) -> str:
    parts = []
    background = None
    for element in feature["elements"]:
        if element["type"] == "background":
            background = element
        else:
            parts.append(_scenario(element, background))
            background = None
    return (
        f'<section><h2>{escape(feature["name"])}<small>{escape(feature["uri"])}</small></h2>'
        f'{"".join(parts)}</section>'
    )


def render(report: Report, summary: Summary, duration: float) -> str:
    """The report page for `report`; every text is escaped."""
    return PAGE.substitute(
        totals=escape(format_summary(summary, duration)),
        features="\n".join(_feature(f) for f in report.features),
    )
