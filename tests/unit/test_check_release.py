"""Release validation against real temporary repositories, including divergent histories."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/check_release.py"


def git(root, *args):
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"},
    )
    return result.stdout.strip()


@pytest.fixture
def release_repo(tmp_path):
    git(tmp_path, "init", "-b", "main")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-10-17\n\n- First release.\n"
        "\n## [0.0.1] - 2026-10-16\n\n- Earlier release.\n", encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "test: prepare release")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(tmp_path, "tag", "v0.1.0")
    return tmp_path


def check(root, tag="v0.1.0"):
    return subprocess.run(
        [sys.executable, str(SCRIPT), tag], cwd=root, capture_output=True, text=True, check=False,
    )


def test_release_prints_only_the_requested_changelog_section(release_repo):
    result = check(release_repo)
    assert result.returncode == 0, result.stderr
    assert "## [0.1.0] - 2026-10-17" in result.stdout and "First release." in result.stdout
    assert "Earlier release." not in result.stdout and "Unreleased" not in result.stdout


@pytest.mark.parametrize("tag", ["0.1.0", "v1.2", "v01.2.3", "v1.2.3junk", "main", "v1.2.3;id"])
def test_invalid_tag_has_its_own_exit_code(release_repo, tag):
    result = check(release_repo, tag)
    assert result.returncode == 2 and "invalid release tag" in result.stderr


def test_version_mismatch_has_its_own_exit_code(release_repo):
    result = check(release_repo, "v0.2.0")
    assert result.returncode == 3 and "does not match" in result.stderr


def test_commit_only_on_develop_cannot_release(release_repo):
    git(release_repo, "switch", "-c", "develop")
    (release_repo / "new.txt").write_text("development", encoding="utf-8")
    git(release_repo, "add", ".")
    git(release_repo, "commit", "-m", "feat: develop only")
    git(release_repo, "tag", "-f", "v0.1.0")
    result = check(release_repo)
    assert result.returncode == 4 and "origin/main" in result.stderr


def test_missing_origin_main_fails_closed(release_repo):
    git(release_repo, "update-ref", "-d", "refs/remotes/origin/main")
    result = check(release_repo)
    assert result.returncode == 4 and "origin/main" in result.stderr


def test_tag_must_point_to_the_checked_out_commit(release_repo):
    (release_repo / "extra.txt").write_text("later", encoding="utf-8")
    git(release_repo, "add", ".")
    git(release_repo, "commit", "-m", "test: later commit")
    git(release_repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    result = check(release_repo)
    assert result.returncode == 4 and "checked-out commit" in result.stderr


@pytest.mark.parametrize("heading", ["## [Unreleased]", "## [0.1.0] - Unreleased", "## [0.1.0] - 2026-02-30"])
def test_changelog_requires_a_real_release_date(release_repo, heading):
    (release_repo / "CHANGELOG.md").write_text(f"# Changelog\n\n{heading}\n\n- Changes.\n", encoding="utf-8")
    result = check(release_repo)
    assert result.returncode == 5 and "dated changelog section" in result.stderr


@pytest.mark.parametrize("version", ["0.2.0a1", "0.2.0b2", "0.2.0rc1"])
def test_prerelease_requires_the_exact_project_version(release_repo, version):
    (release_repo / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    (release_repo / "CHANGELOG.md").write_text(f"## [{version}] - 2026-10-17\n\n- Preview.\n", encoding="utf-8")
    git(release_repo, "add", ".")
    git(release_repo, "commit", "-m", "test: preview")
    git(release_repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(release_repo, "tag", f"v{version}")
    result = check(release_repo, f"v{version}")
    assert result.returncode == 0, result.stderr
    assert "Preview." in result.stdout
