"""Exclusive lock on `results_dir`, so two runs never clean or write the same one (D3)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from behave_hive.errors import HiveError

LOCK_NAME = ".behave-hive.lock"

if os.name == "nt":
    import msvcrt

    def _acquire(fd: int) -> None:
        """Lock the first byte of the file; raise BlockingIOError when another run holds it."""
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BlockingIOError from None

    def _release(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _acquire(fd: int) -> None:
        """Lock the file; raise BlockingIOError when another run holds it."""
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def results_lock(results_dir: Path) -> Iterator[None]:
    """Hold the lock of `results_dir` for the duration of the block."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(results_dir / LOCK_NAME, flags, 0o600)
    except OSError as exc:
        raise HiveError(f"cannot open the results lock in {results_dir}: {exc}") from None
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        try:
            _acquire(fd)
        except BlockingIOError:
            raise HiveError(f"results_dir is in use by another run: {results_dir}") from None
        try:
            yield
        finally:
            _release(fd)
    finally:
        os.close(fd)
