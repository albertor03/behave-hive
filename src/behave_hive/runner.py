"""Batch plans, process execution, cleanup and the `run` orchestration (D3)."""

from __future__ import annotations

import concurrent.futures
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from behave.exception import ConfigError as BehaveConfigError
from behave.exception import TagExpressionError

from behave_hive.batching import Batch, effective_workers, make_batches
from behave_hive.config import HiveConfig, build_behave_config, validate_effective
from behave_hive.discovery import discover_units
from behave_hive.errors import ConfigError, HiveError
from behave_hive.expand import classify_examples, expand_tree
from behave_hive.html_report import render
from behave_hive.lock import results_lock
from behave_hive.merge import merge, to_cucumber
from behave_hive.roots import PathMap, group_by_root, needs_expansion
from behave_hive.summary import exit_code, format_summary, summarize

MANAGED = ("cucumber.json", "report.html", "allure-results", "logs", "tmp")
FAILING = ("failed", "undefined", "pending")
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


# -- plans --------------------------------------------------------------------------


def build_plan(batch: Batch, results_dir: Path, behave_args: list[str], allure: bool) -> Path:
    """Write the locations file and the JSON plan of `batch`; return the plan path."""
    tmp = Path(results_dir).resolve() / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    locations = tmp / f"batch-{batch.index}.locations"
    locations.write_text(
        "".join(
            f"{unit.path}\n" if unit.line is None else f"{unit.path}:{unit.line}\n" for unit in batch.units
        ),
        encoding="utf-8",
    )
    plan = {
        "locations_file": str(locations),
        "behave_args": list(behave_args),
        "cucumber_out": str(tmp / f"batch-{batch.index}.json"),
        "allure_dir": str(tmp / f"allure-batch-{batch.index}") if allure else None,
    }
    plan_path = tmp / f"batch-{batch.index}.plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan_path


def build_command(plan_path: Path) -> list[str]:
    return [sys.executable, "-m", "behave_hive.worker", "--plan", str(plan_path)]


def prepare_jobs(batches: list[Batch], results_dir: Path, behave_args: list[str], allure: bool) -> list[Job]:
    results = Path(results_dir).resolve()
    (results / "logs").mkdir(parents=True, exist_ok=True)
    jobs = []
    for batch in batches:
        plan_path = build_plan(batch, results, behave_args, allure)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        jobs.append(
            Job(
                batch,
                plan_path,
                results / "logs" / f"batch-{batch.index}.log",
                Path(plan["cucumber_out"]),
                Path(plan["allure_dir"]) if plan["allure_dir"] else None,
            )
        )
    return jobs


# -- execution ----------------------------------------------------------------------


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
    try:
        os.killpg(os.getpgid(pid), sig)
    except ProcessLookupError:
        pass


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
    slots: queue.Queue[int] = queue.Queue()
    for slot in range(1, workers + 1):
        slots.put(slot)
    launch_lock = threading.Lock()
    cancel = threading.Event()
    procs: dict[int, object] = {}

    def task(job: Job) -> tuple[BatchOutcome, list[dict] | None]:
        outcome = BatchOutcome(job.batch.index, log_path=job.log_path)
        slot = slots.get()
        try:
            before_launch()
            with launch_lock:
                if cancel.is_set():
                    outcome.interrupted = True
                    return outcome, None
                env = {**os.environ, "BEHAVE_HIVE_WORKER": str(slot), "BEHAVE_HIVE_BATCH": str(job.batch.index)}
                log = open(job.log_path, "wb")
                try:
                    proc = popen(
                        build_command(job.plan_path), cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=True, env=env,
                    )
                except BaseException:
                    log.close()
                    raise
                procs[job.batch.index] = proc
            started = time.monotonic()
            try:
                outcome.returncode = proc.wait()
            finally:
                log.close()
                procs.pop(job.batch.index, None)
            outcome.slot = slot
            outcome.seconds = time.monotonic() - started
        finally:
            slots.put(slot)

        if cancel.is_set() and not job.cucumber_path.exists():
            outcome.interrupted = True
            return outcome, None
        partial = _read_partial(job.cucumber_path)
        outcome.error = _evaluate(job, outcome.returncode, partial)
        if partial is not None:
            outcome.scenarios = len(_scenarios(partial))
            _move_allure(job, results_dir)
        echo(_line(outcome))
        return outcome, partial

    result = ExecutionResult()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = [executor.submit(task, job) for job in jobs]
    try:
        wait(futures)
    except KeyboardInterrupt:
        with launch_lock:
            cancel.set()
            running = list(procs.values())
        result.interrupted = True
        for proc in running:
            kill_group(proc.pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        for proc in running:
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if proc.poll() is None:
                kill_group(proc.pid, signal.SIGKILL)
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


# -- cleanup ------------------------------------------------------------------------


def clean_managed(results_dir: Path) -> None:
    """Delete only what behave-hive manages inside `results_dir`; keep everything else."""
    results_dir = Path(results_dir)
    for name in MANAGED:
        path = results_dir / name
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()


def remove_tmp(results_dir: Path, run_dir: Path | None) -> None:
    """Remove `results_dir/tmp` and the run directory inside `work_dir`."""
    shutil.rmtree(Path(results_dir) / "tmp", ignore_errors=True)
    if run_dir is not None:
        shutil.rmtree(run_dir, ignore_errors=True)


# -- the `run` command --------------------------------------------------------------


def _feature_files(inputs: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for item in inputs:
        files.update(sorted(item.rglob("*.feature")) if item.is_dir() else [item])
    return sorted(files)


def _examples_report(inputs: list[Path], lang: str) -> list[str]:
    """`Examples: <i> inline, <c> from CSV` plus the CSV files in use."""
    inline = csv_tables = 0
    csv_files: list[str] = []
    for feature in _feature_files(inputs):
        for ref in classify_examples(feature.read_text(encoding="utf-8"), lang):
            if ref.kind == "inline":
                inline += 1
                continue
            csv_tables += 1
            csv_file = Path(os.path.normpath(feature.parent / ref.csv_path))
            try:
                csv_file = csv_file.relative_to(Path.cwd())
            except ValueError:
                pass
            if csv_file.as_posix() not in csv_files:
                csv_files.append(csv_file.as_posix())
    return [f"Examples: {inline} inline, {csv_tables} from CSV", *(f"  - {name}" for name in csv_files)]


def _write_json_atomically(path: Path, data: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def run_suite(cfg: HiveConfig, *, keep_tmp: bool = False) -> int:
    """Run the suite described by `cfg`; return the exit code (spec:parallel-runner)."""
    started = time.monotonic()
    inputs = []
    for name in cfg.paths:
        path = Path(name)
        if not path.exists():
            raise HiveError(f"path not found: {name}")
        inputs.append(path)

    try:
        behave_config = build_behave_config(list(cfg.behave_args))
    except (BehaveConfigError, TagExpressionError) as exc:
        raise ConfigError(f"{exc.__class__.__name__}: {exc}") from None
    validate_effective(behave_config, list(cfg.behave_args))
    lang = behave_config.lang or "en"

    roots = group_by_root(inputs)
    results_dir = cfg.results_dir.resolve()
    with results_lock(results_dir):
        clean_managed(results_dir)
        run_dir = cfg.work_dir.resolve() / f"run-{os.getpid()}-{int(time.time() * 1000)}"
        try:
            return _run_locked(cfg, roots, lang, results_dir, run_dir, keep_tmp, started)
        finally:
            if not keep_tmp:
                remove_tmp(results_dir, run_dir)


def _run_locked(cfg, roots, lang, results_dir, run_dir, keep_tmp, started) -> int:
    for line in _examples_report([p for group in roots.values() for p in group], lang):
        print(line)
    if cfg.parallel:
        print(f"Mode: parallel ({cfg.workers} workers, scheme {cfg.scheme})")
    else:
        print("Mode: sequential")

    path_map: dict[Path, Path] = {}
    sources: dict[Path, list] = {}
    units_by_root: dict[Path, list] = {}
    for k, (root, group) in enumerate(roots.items()):
        targets = group
        if needs_expansion(root, lang):
            expanded_root = run_dir / "roots" / str(k) / root.name
            tree = expand_tree(root, expanded_root, lang)
            expanded_root = expanded_root.resolve()
            path_map[expanded_root] = root
            sources.update(tree.sources_by_file)
            targets = [expanded_root / p.relative_to(root) for p in group]
        units_by_root[root] = discover_units(
            targets, list(cfg.behave_args), scheme=cfg.scheme, parallel=cfg.parallel
        )

    batches = make_batches(units_by_root, cfg.workers, cfg.chunk, cfg.parallel)
    if not batches:
        print("No scenarios found")
        return 0

    jobs = prepare_jobs(batches, results_dir, list(cfg.behave_args), allure="allure" in cfg.formats)
    execution = execute_batches(jobs, effective_workers(cfg.workers, cfg.parallel))

    report = merge(execution.partials, PathMap(path_map), sources)
    if "cucumber" in cfg.formats:
        _write_json_atomically(results_dir / "cucumber.json", to_cucumber(report))
    summary = summarize(report)
    duration = time.monotonic() - started
    if "html" in cfg.formats:
        (results_dir / "report.html").write_text(render(report, summary, duration), encoding="utf-8")

    print(format_summary(summary, duration))
    for outcome in execution.batch_errors:
        print(f"Batch {outcome.index} error: {outcome.error}")
    if execution.interrupted:
        return 130
    return exit_code(summary, batch_errors=len(execution.batch_errors))
