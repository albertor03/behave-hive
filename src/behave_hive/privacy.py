"""Rewrite run-internal and user-identifying path prefixes at report boundaries."""

from __future__ import annotations

import re
from pathlib import Path, PurePath, PureWindowsPath


def user_home() -> Path | None:
    """The home directory, or None when the environment does not define one."""
    try:
        return Path.home()
    except RuntimeError:
        return None


# One separator, or two when the text went through JSON or `repr`; then the rest of the path
WINDOWS_SEPARATOR = r"[\\/]{1,2}"
WINDOWS_TAIL = rf"(?:{WINDOWS_SEPARATOR}[^\s\\/\"':),;\]]+)*"


def _with_forward_slashes(text: str, path: PurePath | None) -> str:
    """Rewrite a Windows `path` and what follows it (backslashes, doubled ones, any case) with `/`."""
    if not isinstance(path, PureWindowsPath):
        return text
    prefix = re.escape(path.drive) + "".join(WINDOWS_SEPARATOR + re.escape(part) for part in path.parts[1:])

    def replace(match: re.Match[str]) -> str:
        return path.as_posix() + re.sub(r"[\\/]+", "/", match["tail"])

    return re.sub(rf"(?<!\w){prefix}(?P<tail>{WINDOWS_TAIL})(?![\w.-])", replace, text, flags=re.IGNORECASE)


def scrub(text: str, cwd: PurePath, home: PurePath | None) -> str:
    """Replace whole path prefixes, longest first, without rewriting unrelated text."""
    text = _with_forward_slashes(_with_forward_slashes(text, cwd), home)
    replacements = {home.as_posix(): "~"} if home is not None else {}
    replacements[cwd.as_posix()] = "."
    prefixes = "|".join(re.escape(p) for p in sorted(replacements, key=len, reverse=True))
    pattern = rf"(?<![\w/.-])(?P<prefix>{prefixes})(?=/|$|[\s\"':),;\]])(?P<slash>/?)"

    def replace(match: re.Match[str]) -> str:
        target = replacements[match["prefix"]]
        if match["slash"]:
            return "" if target == "." else target + "/"
        return target

    return re.sub(pattern, replace, text)
