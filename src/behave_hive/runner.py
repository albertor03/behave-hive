"""Batch plans, process execution, cleanup and the `run` orchestration (D3)."""

from __future__ import annotations

import datetime
import importlib.metadata
import json
import os
import platform
import shutil
import time
from contextlib import suppress
from pathlib import Path

from behave.exception import ConfigError as BehaveConfigError
from behave.exception import TagExpressionError

from behave_hive.batching import Batch, effective_workers, make_batches
from behave_hive.config import HiveConfig, build_behave_config, validate_effective
from behave_hive.discovery import discover_units
from behave_hive.errors import ConfigError, HiveError
from behave_hive.execution import Job, execute_batches
from behave_hive.expand import classify_examples, expand_tree
from behave_hive.html_report import REPORT_MARKER, RunInfo, render
from behave_hive.lock import results_lock
from behave_hive.merge import merge, to_cucumber
from behave_hive.privacy import scrub, user_home
from behave_hive.roots import PathMap, feature_files, group_by_root, needs_expansion
from behave_hive.summary import exit_code, format_summary, summarize

MANAGED = ("cucumber.json", "report.html", "allure-results", "logs", "tmp")
MARKER_SCAN_BYTES = 2048


# -- plans --------------------------------------------------------------------------


def _write_private(path: Path, text: str) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
    except OSError as exc:
        raise HiveError(f"cannot write private run file {path}: {exc}") from None


def build_plan(
    batch: Batch,
    results_dir: Path,
    behave_args: list[str],
    allure: bool,
    path_map: dict[Path, Path] | None = None,
    environment: dict[str, str] | None = None,
) -> Path:
    """Write the locations file and the JSON plan of `batch`; return the plan path."""
    tmp = Path(results_dir).resolve() / "tmp"
    tmp.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp.chmod(0o700)
    locations = tmp / f"batch-{batch.index}.locations"
    _write_private(
        locations,
        "".join(
            f"{unit.path}\n" if unit.line is None else f"{unit.path}:{unit.line}\n" for unit in batch.units
        ),
    )
    plan = {
        "locations_file": str(locations),
        "behave_args": list(behave_args),
        "cucumber_out": str(tmp / f"batch-{batch.index}.json"),
        "allure_dir": str(tmp / f"allure-batch-{batch.index}") if allure else None,
        "path_map": {str(expanded): str(original) for expanded, original in (path_map or {}).items()},
        "environment": environment or {},
    }
    plan_path = tmp / f"batch-{batch.index}.plan.json"
    _write_private(plan_path, json.dumps(plan, indent=2))
    return plan_path


def prepare_jobs(
    batches: list[Batch],
    results_dir: Path,
    behave_args: list[str],
    allure: bool,
    path_map: dict[Path, Path] | None = None,
    environment: dict[str, str] | None = None,
) -> list[Job]:
    results = Path(results_dir).resolve()
    (results / "logs").mkdir(parents=True, exist_ok=True)
    jobs = []
    for batch in batches:
        plan_path = build_plan(batch, results, behave_args, allure, path_map, environment)
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


def remove_stale_report(path: Path) -> None:
    """Delete `path` only when it is a regular file that behave-hive generated (marker in its head)."""
    if path.is_symlink() or not path.is_file():
        return
    try:
        with open(path, "rb") as stream:
            head = stream.read(MARKER_SCAN_BYTES)
    except OSError:
        return
    if REPORT_MARKER.encode() in head:
        path.unlink(missing_ok=True)


def remove_tmp(results_dir: Path, run_dir: Path | None) -> None:
    """Remove `results_dir/tmp` and the run directory inside `work_dir`."""
    shutil.rmtree(Path(results_dir) / "tmp", ignore_errors=True)
    if run_dir is not None:
        shutil.rmtree(run_dir, ignore_errors=True)


# -- the `run` command --------------------------------------------------------------


def _examples_report(inputs: list[Path], lang: str) -> list[str]:
    """`Examples: <i> inline, <c> from CSV` plus the CSV files in use."""
    inline = csv_tables = 0
    csv_files: list[str] = []
    for feature in feature_files(inputs):
        for ref in classify_examples(feature.read_text(encoding="utf-8"), lang):
            if ref.kind == "inline":
                inline += 1
                continue
            csv_tables += 1
            csv_file = Path(os.path.normpath(feature.parent / ref.csv_path))
            with suppress(ValueError):
                csv_file = csv_file.relative_to(Path.cwd())
            if csv_file.as_posix() not in csv_files:
                csv_files.append(csv_file.as_posix())
    return [f"Examples: {inline} inline, {csv_tables} from CSV", *(f"  - {name}" for name in csv_files)]


def _write_json_atomically(path: Path, data: object) -> None:
    write_text_atomically(path, json.dumps(data, ensure_ascii=False, indent=2))


def write_text_atomically(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def run_suite(cfg: HiveConfig, *, keep_tmp: bool = False, argv: list[str] | None = None) -> int:
    """Run the suite described by `cfg`; return the exit code (spec:parallel-runner)."""
    started = time.monotonic()
    started_at = datetime.datetime.now()
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
            return _run_locked(cfg, roots, lang, results_dir, run_dir, keep_tmp, (started, started_at), argv or [])
        finally:
            if not keep_tmp:
                remove_tmp(results_dir, run_dir)


def _environment(cfg: HiveConfig, workers: int) -> dict[str, str]:
    """The run context written to Allure's `environment.properties`."""
    return {
        "behave-hive": importlib.metadata.version("behave-hive"),
        "behave": importlib.metadata.version("behave"),
        "python": platform.python_version(),
        "mode": "parallel" if cfg.parallel else "sequential",
        "workers": str(workers),
        "scheme": cfg.scheme,
    }


def _prepare_roots(cfg, roots, lang, run_dir):
    """Expand the roots that need it and discover their units: (path map, row sources, units by root)."""
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
    return path_map, sources, units_by_root


def _run_info(environment: dict[str, str], started_at: datetime.datetime, argv: list[str]) -> RunInfo:
    """What the HTML page says about the run; the command never shows the user's home or project path."""
    command = " ".join(["behave-hive", *argv])
    return RunInfo(
        started=started_at.strftime("%Y-%m-%d %H:%M:%S"),
        parallel=environment["mode"] == "parallel",
        workers=int(environment["workers"]),
        scheme=environment["scheme"],
        behave_hive=environment["behave-hive"],
        behave=environment["behave"],
        python=environment["python"],
        command=scrub(command, PathMap({}), Path.cwd(), user_home()),
    )


def _write_html(cfg, report, summary, duration, run) -> None:
    try:
        cfg.report_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomically(
            cfg.report_path, render(report, summary, duration, report_name=cfg.report_name, run=run)
        )
    except OSError as exc:
        raise HiveError(f"cannot write HTML report to {cfg.report_path}: {exc}") from None


def _run_locked(cfg, roots, lang, results_dir, run_dir, keep_tmp, clock, argv) -> int:
    started, started_at = clock
    if "html" in cfg.formats:
        remove_stale_report(cfg.report_path)
    for line in _examples_report([p for group in roots.values() for p in group], lang):
        print(line)
    if cfg.parallel:
        print(f"Mode: parallel ({cfg.workers} workers, scheme {cfg.scheme})")
    else:
        print("Mode: sequential")

    path_map, sources, units_by_root = _prepare_roots(cfg, roots, lang, run_dir)

    batches = make_batches(units_by_root, cfg.workers, cfg.chunk, cfg.parallel)
    if not batches:
        print("No scenarios found")
        return 0

    workers = effective_workers(cfg.workers, cfg.parallel)
    environment = _environment(cfg, workers)
    jobs = prepare_jobs(
        batches, results_dir, list(cfg.behave_args), allure="allure" in cfg.formats, path_map=path_map,
        environment=environment,
    )
    execution = execute_batches(jobs, workers)

    report = merge(execution.partials, PathMap(path_map), sources)
    if "cucumber" in cfg.formats:
        _write_json_atomically(results_dir / "cucumber.json", to_cucumber(report))
    summary = summarize(report)
    duration = time.monotonic() - started
    if "html" in cfg.formats:
        _write_html(cfg, report, summary, duration, _run_info(environment, started_at, argv))

    print(format_summary(summary, duration))
    for outcome in execution.batch_errors:
        print(f"Batch {outcome.index} error: {outcome.error}")
    if execution.interrupted:
        return 130
    return exit_code(summary, batch_errors=len(execution.batch_errors))
