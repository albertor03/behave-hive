"""Contract for the quality and coverage jobs; extended by the Actions change."""

import re
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


def test_ci_has_six_jobs_safe_concurrency_and_caches():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = set(re.findall(r"^  ([\w-]+):", text.split("\njobs:\n", 1)[1], re.M))
    assert jobs == {"unit", "e2e", "packaging", "quality", "coverage", "actionlint"}
    assert 'os: [ubuntu-latest, macos-latest]' in text
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
