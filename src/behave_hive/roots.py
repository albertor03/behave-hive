"""Features roots (directories with `steps/`) and the `.feature` files under the inputs (D2)."""

from __future__ import annotations

from pathlib import Path

from behave_hive.errors import HiveError


def find_root(path: Path) -> Path:
    """Walk up from `path` to the first directory that contains `steps/`."""
    path = Path(path).resolve()
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if (candidate / "steps").is_dir():
            return candidate
    raise HiveError(f"no features root found for {path}: no parent directory contains 'steps/'")


def feature_files(inputs: list[Path]) -> list[Path]:
    """Absolute `.feature` paths of the inputs, sorted and without duplicates."""
    files: set[Path] = set()
    for item in inputs:
        item = Path(item).resolve()
        files.update(item.rglob("*.feature") if item.is_dir() else [item])
    return sorted(files)


def group_by_root(inputs: list[Path]) -> dict[Path, list[Path]]:
    """Group resolved inputs by their root, in order of first appearance."""
    grouped: dict[Path, list[Path]] = {}
    for item in inputs:
        resolved = Path(item).resolve()
        grouped.setdefault(find_root(resolved), []).append(resolved)
    return grouped
