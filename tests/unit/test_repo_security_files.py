"""Security automation and the documented protection check names."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dependabot_updates_both_ecosystems_without_breaking_allure_pin():
    text = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "pip"' in text
    assert 'package-ecosystem: "github-actions"' in text
    assert text.count('interval: "weekly"') == 2
    assert text.count('target-branch: "develop"') == 2
    assert text.count("groups:") == 2
    assert 'dependency-name: "allure-behave"' in text
    assert '"version-update:semver-major"' in text and '"version-update:semver-minor"' in text


def test_dependency_review_rejects_high_severity_and_unapproved_licenses():
    text = (ROOT / ".github/workflows/dependency-review.yml").read_text(encoding="utf-8")
    assert "pull_request:" in text and "actions/dependency-review-action@" in text
    assert "fail-on-severity: high" in text
    assert "MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, PSF-2.0, MPL-2.0" in text


def test_codeql_has_scheduled_python_analysis_and_high_severity_gate():
    text = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    for value in (
        "push:", "pull_request:", 'cron: "17 3 * * 1"', "security-events: write",
        "contents: read", "languages: python", "github/codeql-action/init@",
        "github/codeql-action/analyze@", "wait-for-processing: true", "security_severity_level",
    ):
        assert value in text
