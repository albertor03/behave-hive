"""Validate a release tag and emit its changelog notes (stdlib only, Python 3.11+)."""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
import tomllib
from pathlib import Path

NUMBER = r"(?:0|[1-9][0-9]*)"
TAG = re.compile(rf"v({NUMBER}\.{NUMBER}\.{NUMBER}(?:(?:a|b|rc){NUMBER})?)")


class ReleaseError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def release_version(tag: str) -> str:
    match = TAG.fullmatch(tag)
    if match is None:
        raise ReleaseError(2, f"invalid release tag: {tag!r}; expected vX.Y.Z or vX.Y.ZrcN (aN/bN also supported)")
    return match[1]


def check_version(root: Path, version: str) -> None:
    try:
        actual = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, ValueError, KeyError) as exc:
        raise ReleaseError(3, f"cannot read project version: {exc}") from None
    if actual != version:
        raise ReleaseError(3, f"tag version {version} does not match pyproject.toml version {actual}")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


def check_commit(root: Path, tag: str) -> None:
    try:
        tagged = git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        head = git(root, "rev-parse", "--verify", "HEAD")
        if tagged.returncode or head.returncode or tagged.stdout != head.stdout:
            raise ReleaseError(4, "tag must exist and point to the checked-out commit")
        reachable = git(root, "merge-base", "--is-ancestor", tagged.stdout.strip(), "refs/remotes/origin/main")
    except OSError as exc:
        raise ReleaseError(4, f"cannot verify origin/main: {exc}") from None
    if reachable.returncode:
        raise ReleaseError(4, "tagged commit is not reachable from origin/main (fetch origin/main first)")


def changelog_notes(root: Path, version: str) -> str:
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise ReleaseError(5, f"cannot read dated changelog section: {exc}") from None
    match = re.search(
        rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})[ \t]*\n(.*?)(?=^## |\Z)",
        text, re.M | re.S,
    )
    if match is None:
        raise ReleaseError(5, f"missing dated changelog section for {version}")
    try:
        datetime.date.fromisoformat(match[1])
    except ValueError:
        raise ReleaseError(5, f"invalid date in dated changelog section for {version}") from None
    return match[0].strip() + "\n"


def main(args: list[str] | None = None) -> int:
    args = sys.argv[1:] if args is None else args
    try:
        if len(args) != 1:
            raise ReleaseError(2, "usage: check_release.py vX.Y.Z")
        tag = args[0]
        version = release_version(tag)
        root = Path.cwd()
        check_version(root, version)
        check_commit(root, tag)
        sys.stdout.write(changelog_notes(root, version))
    except ReleaseError as exc:
        sys.stderr.write(f"release check: {exc}\n")
        return exc.code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
