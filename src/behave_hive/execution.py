"""Process execution of the planned batches: launch, wait, interrupt and collect (D3)."""

from __future__ import annotations

import concurrent.futures
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack, suppress
from dataclasses import dataclass, field
from pathlib import Path

from behave_hive.batching import Batch
from behave_hive.summary import FAILING

GRACE_SECONDS = 5


@dataclass(frozen=True)
class Job:
    """A batch ready to launch: its plan and where its outputs go."""

    batch: Batch
    plan_path: Path
    log_path: Path
    cucumber_path: Path
    allure_dir: Path | None


@dataclass
class BatchOutcome:
    index: int
    slot: int | None = None
    returncode: int | None = None
    seconds: float = 0.0
    log_path: Path | None = None
    scenarios: int = 0
    error: str | None = None
    interrupted: bool = False


@dataclass
class ExecutionResult:
    outcomes: list[BatchOutcome] = field(default_factory=list)
    partials: list[list[dict]] = field(default_factory=list)
    interrupted: bool = False

    @property
    def batch_errors(self) -> list[BatchOutcome]:
        return [o for o in self.outcomes if o.error]


def build_command(plan_path: Path) -> list[str]:
    return [sys.executable, "-m", "behave_hive.worker", "--plan", str(plan_path)]


def _read_partial(path: Path) -> list[dict] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def _scenarios(partial: list[dict]) -> list[dict]:
    return [e for f in partial for e in f.get("elements", []) if e.get("type") == "scenario"]


def _evaluate(job: Job, returncode: int | None, partial: list[dict] | None) -> str | None:
    """The infrastructure error of a batch, if any (spec:parallel-runner/Batch error)."""
    if partial is None:
        return f"partial result missing or invalid (log: {job.log_path})"
    failing = any(s.get("x-behave-hive", {}).get("status") in FAILING for s in _scenarios(partial))
    if returncode != 0 and not failing:
        return f"behave exited with code {returncode} without failed scenarios (log: {job.log_path})"
    return None


def _move_allure(job: Job, results_dir: Path) -> None:
    if job.allure_dir is None or not job.allure_dir.is_dir():
        return
    target = results_dir / "allure-results"
    target.mkdir(parents=True, exist_ok=True)
    for path in job.allure_dir.iterdir():
        os.replace(path, target / path.name)


def _kill_group(pid: int, sig: int) -> None:
    with suppress(ProcessLookupError):
        os.killpg(os.getpgid(pid), sig)


class BatchPool:
    """Owns the slot queue, the launch lock, the cancel event and the process table."""

    def __init__(
        self,
        workers: int,
        *,
        results_dir: Path,
        cwd: Path,
        popen: Callable,
        echo: Callable[[str], None],
        before_launch: Callable[[], None],
    ):
        self._slots: queue.Queue[int] = queue.Queue()
        for slot in range(1, workers + 1):
            self._slots.put(slot)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._procs: dict[int, subprocess.Popen] = {}
        self._results_dir = results_dir
        self._cwd = cwd
        self._popen = popen
        self._echo = echo
        self._before_launch = before_launch

    def run(self, job: Job) -> tuple[BatchOutcome, list[dict] | None]:
        outcome = BatchOutcome(job.batch.index, log_path=job.log_path)
        slot = self._slots.get()
        try:
            launched = self._execute(job, slot, outcome)
        finally:
            self._slots.put(slot)
        return self._finish(job, outcome) if launched else (outcome, None)

    def _execute(self, job: Job, slot: int, outcome: BatchOutcome) -> bool:
        """Launch the batch and wait for it; False when the run was interrupted before the launch."""
        with ExitStack() as resources:
            self._before_launch()
            with self._lock:
                if self._cancel.is_set():
                    outcome.interrupted = True
                    return False
                log = resources.enter_context(open(job.log_path, "wb"))
                proc = self._launch(job, slot, log)
            started = time.monotonic()
            try:
                outcome.returncode = proc.wait()
            finally:
                with self._lock:
                    self._procs.pop(job.batch.index, None)
            outcome.slot = slot
            outcome.seconds = time.monotonic() - started
        return True

    def _launch(self, job: Job, slot: int, log):
        """Start the batch process; the caller holds the launch lock."""
        env = {**os.environ, "BEHAVE_HIVE_WORKER": str(slot), "BEHAVE_HIVE_BATCH": str(job.batch.index)}
        proc = self._popen(
            build_command(job.plan_path), cwd=str(self._cwd), stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=env,
        )
        self._procs[job.batch.index] = proc
        return proc

    def _finish(self, job: Job, outcome: BatchOutcome) -> tuple[BatchOutcome, list[dict] | None]:
        if self._cancel.is_set() and not job.cucumber_path.exists():
            outcome.interrupted = True
            return outcome, None
        partial = _read_partial(job.cucumber_path)
        outcome.error = _evaluate(job, outcome.returncode, partial)
        if partial is not None:
            outcome.scenarios = len(_scenarios(partial))
            _move_allure(job, self._results_dir)
        self._echo(_line(outcome))
        return outcome, partial

    def interrupt(self, kill_group: Callable[[int, int], None], grace: float) -> None:
        """Stop launching, ask every running group to end and kill the ones that ignore it."""
        with self._lock:
            self._cancel.set()
            running = list(self._procs.values())
            for proc in running:
                if proc.poll() is None:
                    kill_group(proc.pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        for proc in running:
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            with self._lock:
                if proc.poll() is None:
                    kill_group(proc.pid, signal.SIGKILL)


def execute_batches(
    jobs: list[Job],
    workers: int,
    *,
    cwd: Path | None = None,
    popen: Callable = subprocess.Popen,
    echo: Callable[[str], None] = print,
    before_launch: Callable[[], None] = lambda: None,
    wait: Callable = concurrent.futures.wait,
    kill_group: Callable[[int, int], None] = _kill_group,
    grace: float = GRACE_SECONDS,
) -> ExecutionResult:
    """Run every job in its own process, never more than `workers` at a time (D3)."""
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    results_dir = jobs[0].plan_path.parent.parent if jobs else cwd
    pool = BatchPool(workers, results_dir=results_dir, cwd=cwd, popen=popen, echo=echo, before_launch=before_launch)

    result = ExecutionResult()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = [executor.submit(pool.run, job) for job in jobs]
    try:
        wait(futures)
    except KeyboardInterrupt:
        result.interrupted = True
        pool.interrupt(kill_group, grace)
    finally:
        executor.shutdown(wait=True)

    for future in futures:
        outcome, partial = future.result()
        result.outcomes.append(outcome)
        if partial is not None and not outcome.interrupted:
            result.partials.append(partial)
    result.outcomes.sort(key=lambda o: o.index)
    return result


def _line(outcome: BatchOutcome) -> str:
    state = "error" if outcome.error else ("passed" if outcome.returncode == 0 else "failed")
    noun = "scenario" if outcome.scenarios == 1 else "scenarios"
    return (
        f"batch {outcome.index} · worker {outcome.slot} · {outcome.scenarios} {noun} · "
        f"{state} · {outcome.seconds:.1f}s"
    )
