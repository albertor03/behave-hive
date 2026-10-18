"""Rewrite run-internal and user-identifying path prefixes at report boundaries."""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path

from behave_hive.roots import PathMap


def _display(path: Path, cwd: Path, home: Path) -> str:
    if path.is_relative_to(cwd):
        return path.relative_to(cwd).as_posix()
    if path.is_relative_to(home):
        return (Path("~") / path.relative_to(home)).as_posix()
    return path.as_posix()


def scrub(text: str, path_map: PathMap, cwd: Path, home: Path) -> str:
    """Replace whole path prefixes, longest first, without rewriting unrelated text."""
    replacements = {home.as_posix(): "~", cwd.as_posix(): "."}
    for expanded, original in path_map.items():
        target = _display(Path(original), cwd, home)
        replacements[expanded] = target
        with suppress(ValueError):
            replacements[Path(expanded).relative_to(cwd).as_posix()] = target
    prefixes = "|".join(re.escape(p) for p in sorted(replacements, key=len, reverse=True))
    pattern = rf"(?<![\w/.-])(?P<prefix>{prefixes})(?=/|$|[\s\"':),;\]])(?P<slash>/?)"

    def replace(match: re.Match[str]) -> str:
        target = replacements[match["prefix"]]
        if match["slash"]:
            return "" if target == "." else target + "/"
        return target

    return re.sub(pattern, replace, text)
