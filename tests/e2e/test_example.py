"""Runs example/ with Playwright through the real CLI (needs chromium)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

EXAMPLE = Path(__file__).resolve().parents[2] / "example"


@pytest.fixture
def example(tmp_path):
    target = tmp_path / "example"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns("reports", ".behave-hive", "__pycache__"))
    return target


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
    assert len(found) == 7
    assert len(data) == 1 and data[0]["uri"] == "features/login.feature"
    reports = example / "reports"
    assert len(list((reports / "allure-results").glob("*-result.json"))) == 7
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
def test_allure_generate_reports_seven_results(example):
    assert hive(example, "--parallel").returncode == 0
    generated = subprocess.run(
        ["npx", "--yes", "allure@3", "generate", "reports/allure-results"],
        cwd=example, capture_output=True, text=True, timeout=600,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    summaries = list(example.rglob("summary.json"))
    assert summaries, generated.stdout
    assert json.loads(summaries[0].read_text(encoding="utf-8"))["stats"]["total"] == 7
