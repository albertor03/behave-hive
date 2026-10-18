"""Release ordering and privilege boundaries without publishing anything."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workflow():
    return (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")


def job(text, name):
    return re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)", text.split("\njobs:\n", 1)[1], re.M | re.S).group(1)


def test_release_verifies_then_builds_once_and_defaults_to_rehearsal(workflow):
    for value in ('tags: ["v*"]', "workflow_dispatch:", "dry_run:", "type: boolean", "default: true"):
        assert value in workflow
    assert "group: release" in workflow and "cancel-in-progress: false" in workflow
    assert "check_release.py" in job(workflow, "verify")
    assert "fetch-depth: 0" in job(workflow, "verify")
    assert "needs: verify" in job(workflow, "build")
    assert workflow.count("python -m build") == 1
    assert "twine check dist/*" in job(workflow, "build") and "name: dist" in job(workflow, "build")


def test_release_installs_the_same_artifact_with_both_installers(workflow):
    body = job(workflow, "test-install")
    assert "needs: build" in body and "installer: [pip, uv]" in body
    assert "actions/download-artifact@" in body and "name: dist" in body
    assert 'pip install dist/*.whl' in body and 'uv pip install --python' in body
    assert 'behave-hive --version' in body and 'behave-hive $VERSION' in body
    assert "python -m venv" in body


def test_only_publish_has_oidc_and_never_publishes_a_dry_run(workflow):
    body = job(workflow, "publish")
    for value in (
        "needs: test-install", "environment: pypi", "id-token: write", "pypa/gh-action-pypi-publish@",
        "github.ref_type == 'tag'", "github.event_name == 'push' || !inputs.dry_run", "name: dist",
    ):
        assert value in body
    assert workflow.count("id-token: write") == 1
    assert "password:" not in workflow and "secrets." not in workflow
    assert workflow.count("contents: write") == 1


def test_github_release_uses_changelog_notes_and_attaches_built_files(workflow):
    body = job(workflow, "github-release")
    for value in ("needs: publish", "contents: write", "gh release create", "--notes-file release-notes.md", "dist/*"):
        assert value in body
    assert "name: release-notes" in body and "name: dist" in body
