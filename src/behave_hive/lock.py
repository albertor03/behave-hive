"""Exclusive lock on `results_dir`, so two runs never clean or write the same one (D3)."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from behave_hive.errors import HiveError

LOCK_NAME = ".behave-hive.lock"


@contextmanager
def results_lock(results_dir: Path) -> Iterator[None]:
    """Hold the lock of `results_dir` for the duration of the block."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(results_dir / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HiveError(f"results_dir is in use by another run: {results_dir}") from None
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
