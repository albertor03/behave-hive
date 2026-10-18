"""Contract for the quality and coverage jobs; extended by the Actions change."""

import json
import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_quality_and_coverage_jobs_use_declared_dev_tools():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for job in ("quality", "coverage"):
        assert f"  {job}:\n" in workflow
    for command in (
        'pip install -e ".[dev]"', 'pip install -e ".[dev,allure]"',
        "ruff check src tests", "pylint src", "pip-audit --local --skip-editable",
        'pytest -m "not e2e and not packaging" --cov',
    ):
        assert command in workflow


@pytest.mark.parametrize("path", sorted((ROOT / ".github/workflows").glob("*.yml")), ids=lambda p: p.name)
def test_actions_are_pinned_and_workflows_are_bounded(path):
    text = path.read_text(encoding="utf-8")
    assert "pull_request_target" not in text
    assert "permissions:\n  contents: read" in text
    for line in text.splitlines():
        if "uses:" in line and "uses: ./" not in line:
            assert re.fullmatch(r"\s*- uses: [\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+\s*", line), line
    jobs = re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)", text.split("\njobs:\n", 1)[1], re.M | re.S)
    assert jobs
    for name, body in jobs:
        assert re.search(r"^    timeout-minutes: \d+$", body, re.M), name


def test_ci_jobs_concurrency_and_caches():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = set(re.findall(r"^  ([\w-]+):", text.split("\njobs:\n", 1)[1], re.M))
    assert jobs == {
        "unit", "e2e", "e2e-windows", "packaging", "packaging-windows", "quality", "measure", "coverage", "actionlint",
    }
    assert 'os: [ubuntu-latest, macos-latest, windows-latest]' in text
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in text
    assert "group: ci-${{ github.workflow }}-${{ github.ref }}" in text
    assert "cancel-in-progress: true" in text
    assert "cache: pip" in text and "cache-dependency-path: pyproject.toml" in text
    assert "path: ~/.cache/ms-playwright" in text
    assert "playwright-${{ runner.os }}-${{ hashFiles('pyproject.toml') }}" in text
    assert "playwright install-deps chromium" in text
    assert "actionlint -color .github/workflows/*.yml" in text
    assert "sha256sum --check" in text


def test_diagnostic_artifacts_are_uploaded_even_on_failure():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for job in ("e2e", "coverage"):
        body = re.search(rf"^  {job}:\n(.*?)(?=^  [\w-]+:|\Z)", text, re.M | re.S).group(1)
        assert "actions/upload-artifact@" in body
        assert "if: always()" in body and "retention-days: 7" in body
    assert "BEHAVE_HIVE_E2E_KEEP:" in text
    assert "coverage.txt" in text and ".coverage" in text


def job(name):
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)", text, re.M | re.S).group(1)


def coverage_job():
    return job("coverage")


def test_windows_runs_unit_e2e_packaging_and_measures_coverage():
    assert "windows-latest" in job("unit")
    assert "runs-on: windows-latest" in job("e2e-windows") and "pytest -m e2e" in job("e2e-windows")
    assert "runs-on: windows-latest" in job("packaging-windows") and "pytest -m packaging" in job("packaging-windows")
    measure = job("measure")
    assert "os: [ubuntu-latest, windows-latest]" in measure
    assert "--cov-fail-under=0" in measure and "name: coverage-data-${{ matrix.os }}" in measure
    assert "include-hidden-files: true" in measure and "if: always()" in measure


def test_exact_coverage_evidence_combines_both_platforms_checks_and_is_always_retained():
    body = coverage_job()
    assert "needs: measure" in body
    assert 'python-version: "3.14"' in body
    assert "pattern: coverage-data-*" in body
    assert "python -m coverage combine .artifacts/data/*/.coverage" in body
    for report in ("coverage json --fail-under=0", "coverage xml --fail-under=0", "| tee .artifacts/coverage.txt"):
        assert report in body
    check = re.search(r"      - name: Check exact coverage counters\n(.*?)(?=^      - |\Z)", body, re.M | re.S)
    assert check and "if: always()" in check.group(1)
    upload = body.split("      - uses: actions/upload-artifact@", 1)[1]
    assert "if: always()" in upload and "retention-days: 7" in upload
    for artifact in (".coverage", "coverage.xml", "coverage.txt", "coverage.json"):
        assert f"            .artifacts/{artifact}\n" in upload
    assert body.index("coverage combine") < check.start() < body.index("actions/upload-artifact@")


def test_coverage_paths_treat_linux_and_windows_checkouts_as_the_same_files():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]["paths"]
    assert config["source"] == ["src/behave_hive", "*/src/behave_hive", "*\\src\\behave_hive"]


@pytest.mark.parametrize("gap", ["statement", "branch", "excluded", "missing-report", "complete"])
def test_ci_counter_check_uses_exact_counts_and_preserves_failure(tmp_path, gap):
    body = coverage_job()
    step = re.search(r"      - name: Check exact coverage counters\n(.*?)(?=^      - |\Z)", body, re.M | re.S)
    assert step, "CI needs an always-run exact counter check"
    script = textwrap.dedent(step.group(1).split("run: |\n", 1)[1])
    code = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    totals = {
        "covered_lines": 100_000, "num_statements": 100_000, "missing_lines": 0,
        "covered_branches": 80, "num_branches": 80, "missing_branches": 0, "excluded_lines": 0,
    }
    if gap == "statement":
        totals.update(covered_lines=99_999, missing_lines=1)
    elif gap == "branch":
        totals.update(covered_branches=79, missing_branches=1)
    elif gap == "excluded":
        totals["excluded_lines"] = 1
    if gap != "missing-report":
        (tmp_path / ".artifacts").mkdir()
        (tmp_path / ".artifacts" / "coverage.json").write_text(json.dumps({"totals": totals}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) == (gap == "complete"), result.stdout + result.stderr
    if gap != "missing-report":
        assert f"Statements: {totals['covered_lines']}/{totals['num_statements']}" in result.stdout
        assert f"Branches: {totals['covered_branches']}/{totals['num_branches']}" in result.stdout
