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
# Wait in short steps: on Windows a blocking wait delays Ctrl+C until it returns
POLL_SECONDS = 0.2
READ_BYTES = 65536


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
    not_run: bool = False  # never launched because an earlier batch failed and `stop` is on


@dataclass
class ExecutionResult:
    outcomes: list[BatchOutcome] = field(default_factory=list)
    partials: list[list[dict]] = field(default_factory=list)
    interrupted: bool = False

    @property
    def batch_errors(self) -> list[BatchOutcome]:
        return [o for o in self.outcomes if o.error]

    @property
    def not_run(self) -> int:
        return sum(1 for o in self.outcomes if o.not_run)


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


def _has_failing(partial: list[dict]) -> bool:
    return any(s.get("x-behave-hive", {}).get("status") in FAILING for s in _scenarios(partial))


def _evaluate(job: Job, returncode: int | None, partial: list[dict] | None, failing: bool) -> str | None:
    """The infrastructure error of a batch, if any (spec:parallel-runner/Batch error)."""
    if partial is None:
        return f"partial result missing or invalid (log: {job.log_path})"
    if returncode != 0 and not failing:
        return f"behave exited with code {returncode} without failed scenarios (log: {job.log_path})"
    return None


def _copy_output(source, log, console) -> None:
    """Copy the batch output as it arrives to its log and, while it works, to the console.

    The pipe is always drained, so a closed console never blocks the batch process.
    """
    while chunk := source.read1(READ_BYTES):
        log.write(chunk)
        log.flush()
        if console is not None:
            try:
                console.write(chunk)
                console.flush()
            except OSError:
                console = None


def _move_allure(job: Job, results_dir: Path) -> None:
    if job.allure_dir is None or not job.allure_dir.is_dir():
        return
    target = results_dir / "allure-results"
    target.mkdir(parents=True, exist_ok=True)
    for path in job.allure_dir.iterdir():
        os.replace(path, target / path.name)


if os.name == "nt":
    TASKKILL = str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe")
    # CTRL_BREAK_EVENT reaches only a process group of its own
    NEW_GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}

    def _kill_group(pid: int, force: bool) -> None:
        """Ask the batch process to stop (Ctrl+Break), or end its whole process tree."""
        if force:
            subprocess.run([TASKKILL, "/T", "/F", "/PID", str(pid)], check=False, capture_output=True)
        else:
            with suppress(OSError):
                os.kill(pid, signal.CTRL_BREAK_EVENT)

else:
    NEW_GROUP = {"start_new_session": True}

    def _kill_group(pid: int, force: bool) -> None:
        """Send SIGTERM, or SIGKILL when `force`, to the whole process group of the batch."""
        with suppress(ProcessLookupError):
            os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)


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
        stop_on_failure: bool = False,
        tee: bool = False,
    ):
        self._slots: queue.Queue[int] = queue.Queue()
        for slot in range(1, workers + 1):
            self._slots.put(slot)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._stop_on_failure = stop_on_failure
        self._tee = tee
        self._stopped = threading.Event()
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
            # The slot is held until the result is evaluated, so a failure is known before the next launch
            return self._finish(job, outcome) if launched else (outcome, None)
        finally:
            self._slots.put(slot)

    def _execute(self, job: Job, slot: int, outcome: BatchOutcome) -> bool:
        """Launch the batch and wait for it; False when the run was interrupted before the launch."""
        with ExitStack() as resources:
            self._before_launch()
            with self._lock:
                if self._cancel.is_set():
                    outcome.interrupted = True
                    return False
                if self._stopped.is_set():
                    outcome.not_run = True
                    return False
                log = resources.enter_context(open(job.log_path, "wb"))
                proc = self._launch(job, slot, log)
                reader = self._start_reader(proc, log)
            started = time.monotonic()
            try:
                outcome.returncode = proc.wait()
            finally:
                with self._lock:
                    self._procs.pop(job.batch.index, None)
            if reader is not None:
                # bounded: a descendant that outlives the batch may keep the pipe open
                reader.join(GRACE_SECONDS)
            outcome.slot = slot
            outcome.seconds = time.monotonic() - started
        return True

    def _launch(self, job: Job, slot: int, log):
        """Start the batch process; the caller holds the launch lock."""
        env = {**os.environ, "BEHAVE_HIVE_WORKER": str(slot), "BEHAVE_HIVE_BATCH": str(job.batch.index)}
        if self._tee:
            # a pipe makes the worker's stdout block-buffered: without this nothing shows while it runs
            env["PYTHONUNBUFFERED"] = "1"
        proc = self._popen(
            build_command(job.plan_path), cwd=str(self._cwd), stdout=subprocess.PIPE if self._tee else log,
            stderr=subprocess.STDOUT, env=env, **NEW_GROUP,
        )
        self._procs[job.batch.index] = proc
        return proc

    def _start_reader(self, proc, log) -> threading.Thread | None:
        """With `tee`, a thread that copies the batch output to the log and the console."""
        if not self._tee:
            return None
        console = getattr(sys.stdout, "buffer", None)
        reader = threading.Thread(target=_copy_output, args=(proc.stdout, log, console), daemon=True)
        reader.start()
        return reader

    def _finish(self, job: Job, outcome: BatchOutcome) -> tuple[BatchOutcome, list[dict] | None]:
        if self._cancel.is_set() and not job.cucumber_path.exists():
            outcome.interrupted = True
            return outcome, None
        partial = _read_partial(job.cucumber_path)
        failing = partial is not None and _has_failing(partial)
        outcome.error = _evaluate(job, outcome.returncode, partial, failing)
        if self._stop_on_failure and (outcome.error or failing):
            self._stopped.set()
        if partial is not None:
            outcome.scenarios = len(_scenarios(partial))
            _move_allure(job, self._results_dir)
        self._echo(_line(outcome))
        return outcome, partial

    def interrupt(self, kill_group: Callable[[int, bool], None], grace: float) -> None:
        """Stop launching, ask every running group to end and kill the ones that ignore it."""
        with self._lock:
            self._cancel.set()
            running = list(self._procs.values())
            for proc in running:
                if proc.poll() is None:
                    kill_group(proc.pid, False)
        deadline = time.monotonic() + grace
        for proc in running:
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            with self._lock:
                if proc.poll() is None:
                    kill_group(proc.pid, True)


def execute_batches(
    jobs: list[Job],
    workers: int,
    *,
    cwd: Path | None = None,
    popen: Callable = subprocess.Popen,
    echo: Callable[[str], None] = print,
    before_launch: Callable[[], None] = lambda: None,
    wait: Callable = concurrent.futures.wait,
    kill_group: Callable[[int, bool], None] = _kill_group,
    grace: float = GRACE_SECONDS,
    stop_on_failure: bool = False,
    tee: bool = False,
) -> ExecutionResult:
    """Run every job in its own process, never more than `workers` at a time (D3).

    With `stop_on_failure`, no pending batch is launched once a batch has a failing scenario or an
    error; the batches already running finish and are reported. With `tee`, the output of each batch
    is also shown on the console while it runs (sequential mode with output capture disabled).
    """
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    results_dir = jobs[0].plan_path.parent.parent if jobs else cwd
    pool = BatchPool(
        workers, results_dir=results_dir, cwd=cwd, popen=popen, echo=echo, before_launch=before_launch,
        stop_on_failure=stop_on_failure, tee=tee,
    )

    result = ExecutionResult()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = [executor.submit(pool.run, job) for job in jobs]
    try:
        pending = futures
        while pending:
            _, pending = wait(pending, timeout=POLL_SECONDS)
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
