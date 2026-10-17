"""Splits the discovered units into batches, one behave process each (D3)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from behave_hive.discovery import Unit


@dataclass(frozen=True)
class Batch:
    """Consecutive units of a single root; `index` is 1-based across the whole run."""

    index: int
    root: Path
    units: tuple[Unit, ...]


def effective_workers(workers: int, parallel: bool) -> int:
    return workers if parallel else 1


def make_batches(units_by_root: dict[Path, list[Unit]], workers: int, chunk: int, parallel: bool) -> list[Batch]:
    """One batch per root in sequential mode; `chunk`-sized (or `ceil(n/workers)`) ones in parallel."""
    batches: list[Batch] = []
    for root, units in units_by_root.items():
        if not units:
            continue
        if not parallel:
            size = len(units)
        else:
            size = chunk or math.ceil(len(units) / effective_workers(workers, parallel))
        for start in range(0, len(units), size):
            batches.append(Batch(len(batches) + 1, root, tuple(units[start:start + size])))
    return batches
