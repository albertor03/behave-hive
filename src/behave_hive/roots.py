"""Features roots (directories with `steps/`) and the expanded-to-original path map (D2)."""

from __future__ import annotations

from collections.abc import ItemsView
from pathlib import Path
from typing import TypeVar

from behave_hive.errors import HiveError
from behave_hive.expand import classify_examples

PathLike = TypeVar("PathLike", str, Path)


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


def needs_expansion(root: Path, lang: str) -> bool:
    """True if any `.feature` under `root` has a `csv` or `json` Examples table."""
    for feature in sorted(Path(root).rglob("*.feature")):
        text = feature.read_text(encoding="utf-8")
        if any(ref.kind != "inline" for ref in classify_examples(text, lang)):
            return True
    return False


class PathMap:
    """Maps expanded path prefixes to the original ones, and back."""

    def __init__(self, expanded_to_original: dict[Path, Path]) -> None:
        self._forward = {str(k): str(v) for k, v in expanded_to_original.items()}
        self._backward = {str(v): str(k) for k, v in expanded_to_original.items()}

    def to_original(self, path: PathLike) -> PathLike:
        return self._translate(path, self._forward)

    def to_expanded(self, path: PathLike) -> PathLike:
        return self._translate(path, self._backward)

    def items(self) -> ItemsView[str, str]:
        """Read-only view of expanded-to-original prefix pairs."""
        return self._forward.items()

    @staticmethod
    def _translate(path: PathLike, mapping: dict[str, str]) -> PathLike:
        text = str(path)
        for prefix, target in mapping.items():
            if text == prefix or text.startswith(prefix + "/") or text.startswith(prefix + ":"):
                translated = target + text[len(prefix):]
                return Path(translated) if isinstance(path, Path) else translated
        return path
