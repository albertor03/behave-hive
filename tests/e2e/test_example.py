"""Runs example/ with Playwright through the real CLI (needs chromium)."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

EXAMPLE = Path(__file__).resolve().parents[2] / "example"
EXAMPLE_SCENARIOS = 33
EXAMPLE_FEATURES = [
    "features/csv/forms.feature",
    "features/csv/mixed_and_tagged.feature",
    "features/csv/special_characters.feature",
    "features/json/users.feature",
    "features/login.feature",
    "features/structure/background_and_rule.feature",
    "features/structure/step_data.feature",
]


@pytest.fixture
def example(tmp_path, request):
    target = tmp_path / "example"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns("reports", ".behave-hive", "__pycache__"))
    yield target
    keep = os.environ.get("BEHAVE_HIVE_E2E_KEEP")
    reports = target / "reports"
    if keep and reports.is_dir():
        shutil.copytree(reports, Path(keep) / request.node.name, dirs_exist_ok=True)


def hive(example, *args):
    return subprocess.run(
        [sys.executable, "-m", "behave_hive.cli", "run", *args],
        cwd=example, capture_output=True, text=True, timeout=600,
    )


def scenarios(example):
    data = json.loads((example / "reports" / "cucumber.json").read_text(encoding="utf-8"))
    return data, [e for f in data for e in f["elements"] if e["type"] == "scenario"]


def test_ok_parallel_and_sequential_produce_the_three_reports_with_the_same_ids(example):
    parallel = hive(example, "--parallel")
    assert parallel.returncode == 0, parallel.stdout + parallel.stderr
    data, found = scenarios(example)
    assert len(found) == EXAMPLE_SCENARIOS
    assert sorted(f["uri"] for f in data) == EXAMPLE_FEATURES
    reports = example / "reports"
    assert len(list((reports / "allure-results").glob("*-result.json"))) == EXAMPLE_SCENARIOS
    assert (reports / "report.html").is_file()
    parallel_ids = [s["id"] for s in found]

    sequential = hive(example, "--no-parallel")
    assert sequential.returncode == 0, sequential.stdout + sequential.stderr
    _, found = scenarios(example)
    assert [s["id"] for s in found] == parallel_ids


def test_fail_expected_failure_has_an_error_message_and_a_screenshot(example):
    result = hive(example, "--parallel", "--", "--tags=@expected_fail")
    assert result.returncode == 1, result.stdout + result.stderr
    _, found = scenarios(example)
    (failed,) = found
    steps = [s for s in failed["steps"] if s["result"]["status"] == "failed"]
    assert steps and steps[0]["result"]["error_message"]
    assert steps[0]["embeddings"][0]["mime_type"] == "image/png"


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx is not installed")
def test_allure_generate_reports_every_result(example):
    assert hive(example, "--parallel").returncode == 0
    generated = subprocess.run(
        [shutil.which("npx"), "--yes", "allure@3", "generate", "reports/allure-results"],
        cwd=example, capture_output=True, text=True, timeout=600,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    summaries = list(example.rglob("summary.json"))
    assert summaries, generated.stdout
    assert json.loads(summaries[0].read_text(encoding="utf-8"))["stats"]["total"] == EXAMPLE_SCENARIOS


def test_keep_preserves_reports_when_a_test_fails(tmp_path, monkeypatch):
    keep = tmp_path / "kept"
    monkeypatch.setenv("BEHAVE_HIVE_E2E_KEEP", str(keep))
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('example_fixtures', {str(Path(__file__).resolve())!r})\n"
        "module = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n"
        "example = module.example\n"
        "def test_forced_failure(example):\n"
        "    reports = example / 'reports'\n    reports.mkdir()\n"
        "    (reports / 'report.html').write_text('failure evidence')\n"
        "    raise AssertionError('deliberate failure')\n", encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(probe)], cwd=tmp_path,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert (keep / "test_forced_failure/report.html").read_text() == "failure evidence"


def test_diagnostics_failed_row_has_screenshot_attachment_summary_and_run_context(example):
    result = hive(example, "--parallel", "--", "--tags=@expected_fail")
    assert result.returncode == 1, result.stdout + result.stderr
    reports = example / "reports"

    results = [json.loads(p.read_text(encoding="utf-8")) for p in (reports / "allure-results").glob("*-result.json")]
    (failed,) = results
    attached = [a for step in failed["steps"] for a in step.get("attachments", [])]
    assert [a["type"] for a in attached] == ["image/png"]
    assert (reports / "allure-results" / attached[0]["source"]).read_bytes().startswith(b"\x89PNG")
    properties = (reports / "allure-results" / "environment.properties").read_text(encoding="utf-8")
    assert "mode=parallel" in properties and "workers=3" in properties

    page = (reports / "report.html").read_text(encoding="utf-8")
    assert 'class="error-line"' in page and "data:image/png;base64," in page
    assert re.search(r"worker \d+ · batch \d+ · <span class=\"muted\">logs/batch-\d+\.log", page)
    context = dict(re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", page))
    assert context["Mode"] == "parallel, 3 workers, scheme scenario"
    assert str(example) not in page and str(Path.home()) not in page


@pytest.mark.parametrize("config", ["sequential.ini", "feature_scheme.ini", "pyproject.toml"])
def test_every_config_example_runs_the_same_scenarios(example, config):
    result = hive(example, "--config", f"configs/{config}")
    assert result.returncode == 0, result.stdout + result.stderr
    data, found = scenarios(example)
    assert len(found) == EXAMPLE_SCENARIOS
    assert sorted(f["uri"] for f in data) == EXAMPLE_FEATURES
    assert len({s["id"] for s in found}) == EXAMPLE_SCENARIOS


@pytest.mark.parametrize(
    "tag, names",
    [
        ("@smoke", ["Sign in as admin -- @1.1 from a CSV file"]),
        (
            "@regression",
            [
                "Sign in as guest -- @2.1 written by hand",
                "Sign in as other -- @3.1 from another CSV file, with read()",
                "Sign in as admin -- @3.2 from another CSV file, with read()",
            ],
        ),
    ],
)
def test_tags_pick_one_examples_table(example, tag, names):
    result = hive(example, "--", f"--tags={tag}")
    assert result.returncode == 0, result.stdout + result.stderr
    _, found = scenarios(example)
    assert sorted(s["name"] for s in found) == sorted(names)


def test_csv_forms_cover_plain_path_and_both_read_quotes(example):
    result = hive(example, "features/csv/forms.feature")
    assert result.returncode == 0, result.stdout + result.stderr
    _, found = scenarios(example)
    assert sorted({s["name"].split(" -- ")[0] for s in found}) == [
        "plain path - admin",
        "plain path - other",
        "read() with double quotes - admin",
        "read() with double quotes - other",
        "read() with single quotes - admin",
        "read() with single quotes - other",
    ]
    assert len(found) == 6
