"""Contract for the quality and coverage jobs; extended by the Actions change."""

from pathlib import Path

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
