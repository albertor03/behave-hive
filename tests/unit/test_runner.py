import json
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from behave_hive.batching import Batch
from behave_hive.discovery import Unit
from behave_hive.errors import HiveError
from behave_hive.execution import build_command, execute_batches
from behave_hive.html_report import REPORT_MARKER
from behave_hive.runner import (
    build_plan,
    clean_managed,
    prepare_jobs,
    remove_stale_report,
    remove_tmp,
    write_text_atomically,
)

ROOT = Path("/proj/features")


def batch(index=1, n=3, root=ROOT, whole_files=False):
    path = root / "a.feature"
    units = tuple(Unit(path, None if whole_files else 10 + i) for i in range(n))
    return Batch(index, root, units)


# --- 6.3 plan and command ------------------------------------------------------


def test_plan_has_locations_file_with_one_absolute_location_per_unit(tmp_path):
    plan_path = build_plan(batch(2, 3), tmp_path, ["-D", "k=v"], allure=False)
    plan = json.loads(plan_path.read_text())
    assert plan_path == tmp_path / "tmp" / "batch-2.plan.json"
    assert Path(plan["locations_file"]) == tmp_path / "tmp" / "batch-2.locations"
    assert Path(plan["locations_file"]).read_text().splitlines() == [
        f"{ROOT}/a.feature:10", f"{ROOT}/a.feature:11", f"{ROOT}/a.feature:12",
    ]
    assert plan["behave_args"] == ["-D", "k=v"]
    assert Path(plan["cucumber_out"]) == tmp_path / "tmp" / "batch-2.json"
    assert plan["allure_dir"] is None


def test_plan_with_feature_units_lists_only_the_file(tmp_path):
    plan = json.loads(build_plan(batch(1, 1, whole_files=True), tmp_path, [], allure=False).read_text())
    assert Path(plan["locations_file"]).read_text().splitlines() == [f"{ROOT}/a.feature"]


def test_plan_with_allure_has_a_per_batch_allure_dir(tmp_path):
    plan = json.loads(build_plan(batch(4), tmp_path, [], allure=True).read_text())
    assert Path(plan["allure_dir"]) == tmp_path / "tmp" / "allure-batch-4"


def test_plan_paths_are_absolute_even_for_a_relative_results_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan = json.loads(build_plan(batch(1), Path("reports"), [], allure=True).read_text())
    for key in ("locations_file", "cucumber_out", "allure_dir"):
        assert Path(plan[key]).is_absolute()


def test_command_line_stays_short_with_5000_units(tmp_path):
    plan_path = build_plan(batch(1, 5000), tmp_path, [], allure=True)
    command = build_command(plan_path)
    assert len(" ".join(command)) < 4096
    assert command[1:4] == ["-m", "behave_hive.worker", "--plan"]
    assert command[-1] == str(plan_path)


# --- fake processes ------------------------------------------------------------


class Fake:
    """A fake `Popen` that writes the batch result when waited on."""

    def __init__(self, rc=0, scenarios=("passed",), hold=0.0, write_json=True, allure_files=()):
        self.rc, self.scenarios, self.hold = rc, scenarios, hold
        self.write_json, self.allure_files = write_json, allure_files
        self.lock = threading.Lock()
        self.active: dict[int, int] = {}
        self.max_active = 0
        self.calls: list[dict] = []
        self.pids = iter(range(1000, 100000))
        self.killed: list[tuple[int, int]] = []

    def __call__(self, command, **kwargs):
        plan = json.loads(Path(command[-1]).read_text())
        with self.lock:
            pid = next(self.pids)
            slot = int(kwargs["env"]["BEHAVE_HIVE_WORKER"])
            assert slot not in self.active.values(), "two active processes share a slot"
            self.active[pid] = slot
            self.max_active = max(self.max_active, len(self.active))
            self.calls.append({"pid": pid, "plan": plan, **kwargs})
        return FakeProc(self, pid, plan)


class FakeProc:
    def __init__(self, fake, pid, plan):
        self.fake, self.pid, self.plan, self.returncode = fake, pid, plan, None

    def wait(self, timeout=None):
        time.sleep(self.fake.hold)
        if self.fake.write_json:
            elements = [
                {"type": "scenario", "id": f"f;s{i}", "line": i + 1, "x-behave-hive": {"status": s}}
                for i, s in enumerate(self.fake.scenarios)
            ]
            Path(self.plan["cucumber_out"]).write_text(json.dumps([{"uri": "u", "elements": elements}]))
        if self.plan["allure_dir"]:
            allure_dir = Path(self.plan["allure_dir"])
            allure_dir.mkdir(parents=True, exist_ok=True)
            for name in self.fake.allure_files:
                (allure_dir / name).write_text("{}")
        with self.fake.lock:
            self.fake.active.pop(self.pid, None)
        self.returncode = self.fake.rc
        return self.returncode

    def poll(self):
        return self.returncode


def jobs_for(tmp_path, batches, allure=False):
    return prepare_jobs(batches, tmp_path, [], allure=allure)


def execute(tmp_path, fake, batches, workers=2, allure=False, **kwargs):
    return execute_batches(
        jobs_for(tmp_path, batches, allure), workers, cwd=tmp_path, popen=fake, echo=lambda line: None, **kwargs
    )


# --- 6.4 execution -------------------------------------------------------------


def test_execution_never_runs_more_than_workers_processes_at_once(tmp_path):
    fake = Fake(hold=0.03)
    result = execute(tmp_path, fake, [batch(i) for i in range(1, 11)], workers=2)
    assert len(fake.calls) == 10
    assert fake.max_active <= 2
    assert not result.interrupted


def test_execution_slots_are_within_range_and_unique_among_active_processes(tmp_path):
    fake = Fake(hold=0.02)
    execute(tmp_path, fake, [batch(i) for i in range(1, 10)], workers=3)
    slots = {int(c["env"]["BEHAVE_HIVE_WORKER"]) for c in fake.calls}
    assert slots <= {1, 2, 3}


def test_execution_passes_the_one_based_batch_index_and_new_session(tmp_path):
    fake = Fake()
    execute(tmp_path, fake, [batch(i) for i in range(1, 4)], workers=1)
    assert sorted(int(c["env"]["BEHAVE_HIVE_BATCH"]) for c in fake.calls) == [1, 2, 3]
    assert all(c["start_new_session"] is True for c in fake.calls)
    assert all(Path(c["cwd"]) == tmp_path for c in fake.calls)


def test_execution_writes_one_log_per_batch(tmp_path):
    fake = Fake()
    execute(tmp_path, fake, [batch(i) for i in range(1, 4)])
    for i in range(1, 4):
        assert (tmp_path / "logs" / f"batch-{i}.log").is_file()


def test_execution_sequential_two_roots_run_one_after_the_other_with_slot_1(tmp_path):
    fake = Fake(hold=0.02)
    execute(tmp_path, fake, [batch(1, root=Path("/a/features")), batch(2, root=Path("/b/features"))], workers=1)
    assert fake.max_active == 1
    assert [c["env"]["BEHAVE_HIVE_WORKER"] for c in fake.calls] == ["1", "1"]


def test_execution_moves_allure_files_only_for_batches_with_complete_json(tmp_path):
    fake = Fake(allure_files=("a-result.json",))
    execute(tmp_path, fake, [batch(1)], allure=True)
    assert (tmp_path / "allure-results" / "a-result.json").is_file()


def test_execution_does_not_move_allure_files_of_a_batch_without_json(tmp_path):
    fake = Fake(rc=1, write_json=False, allure_files=("a-result.json",))
    execute(tmp_path, fake, [batch(1)], allure=True)
    assert not (tmp_path / "allure-results" / "a-result.json").exists()


def test_execution_outcomes_carry_scenario_counts_and_are_ordered_by_batch(tmp_path):
    fake = Fake(scenarios=("passed", "failed"), rc=1)
    result = execute(tmp_path, fake, [batch(i) for i in range(1, 4)])
    assert [o.index for o in result.outcomes] == [1, 2, 3]
    assert all(o.scenarios == 2 for o in result.outcomes)
    assert len(result.partials) == 3


def test_execution_prints_one_line_per_finished_batch(tmp_path):
    fake = Fake()
    lines = []
    execute_batches(jobs_for(tmp_path, [batch(1), batch(2)]), 1, cwd=tmp_path, popen=fake, echo=lines.append)
    assert len(lines) == 2
    assert "batch 1" in lines[0] and "worker 1" in lines[0] and "1 scenario" in lines[0] and "passed" in lines[0]


# --- 6.5 batch error -----------------------------------------------------------


def test_batch_error_missing_json_is_an_error_even_with_rc_0(tmp_path):
    result = execute(tmp_path, Fake(rc=0, write_json=False), [batch(1)])
    (outcome,) = result.outcomes
    assert outcome.error and "result" in outcome.error
    assert result.batch_errors == [outcome]


def test_batch_error_invalid_json(tmp_path):
    jobs = jobs_for(tmp_path, [batch(1)])

    class Corrupt(Fake):
        def __call__(self, command, **kwargs):
            proc = super().__call__(command, **kwargs)
            Path(proc.plan["cucumber_out"]).write_text("[{")
            return proc

    corrupt = Corrupt(write_json=False)
    result = execute_batches(jobs, 1, cwd=tmp_path, popen=corrupt, echo=lambda line: None)
    assert result.outcomes[0].error


def test_batch_error_nonzero_rc_without_failed_scenarios_is_an_error(tmp_path):
    result = execute(tmp_path, Fake(rc=1, scenarios=("passed",)), [batch(1)])
    assert result.outcomes[0].error
    assert str(tmp_path / "logs" / "batch-1.log") in result.outcomes[0].error


@pytest.mark.parametrize("status", ["failed", "undefined", "pending"])
def test_batch_error_nonzero_rc_with_failing_scenarios_is_not_an_error(tmp_path, status):
    result = execute(tmp_path, Fake(rc=1, scenarios=("passed", status)), [batch(1)])
    assert result.outcomes[0].error is None
    assert result.batch_errors == []


# --- 6.6 cleanup ---------------------------------------------------------------


def make_results(tmp_path):
    results = tmp_path / "reports"
    (results / "allure-results").mkdir(parents=True)
    (results / "allure-results" / "old-result.json").write_text("{}")
    (results / "logs").mkdir()
    (results / "logs" / "batch-1.log").write_text("x")
    (results / "tmp").mkdir()
    (results / "tmp" / "batch-1.json").write_text("x")
    (results / "cucumber.json").write_text("[]")
    (results / "report.html").write_text("<html>")
    (results / "notes.txt").write_text("keep me")
    (results / "other-dir").mkdir()
    (results / "other-dir" / "x.txt").write_text("keep me too")
    return results


def test_cleanup_removes_only_managed_paths(tmp_path):
    results = make_results(tmp_path)
    clean_managed(results)
    assert sorted(p.name for p in results.iterdir()) == ["notes.txt", "other-dir"]
    assert (results / "other-dir" / "x.txt").read_text() == "keep me too"


def test_cleanup_tolerates_an_empty_or_missing_results_dir(tmp_path):
    clean_managed(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    clean_managed(tmp_path / "empty")


def test_cleanup_remove_tmp_deletes_the_tmp_dir_and_the_run_dir(tmp_path):
    results = make_results(tmp_path)
    run_dir = tmp_path / ".behave-hive" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "x").write_text("x")
    remove_tmp(results, run_dir)
    assert not (results / "tmp").exists()
    assert not run_dir.exists()
    assert (results / "cucumber.json").exists()
    assert (tmp_path / ".behave-hive").exists()


def test_cleanup_remove_tmp_tolerates_missing_paths(tmp_path):
    remove_tmp(tmp_path / "reports", None)


# --- 6.12 path_map in the plan ----------------------------------------------------


def test_path_map_is_written_to_the_plan(tmp_path):
    expanded, original = Path("/proj/.behave-hive/run-1/roots/0/features"), Path("/proj/features")
    plan = json.loads(build_plan(batch(1), tmp_path, [], allure=True, path_map={expanded: original}).read_text())
    assert plan["path_map"] == {str(expanded): str(original)}


def test_path_map_defaults_to_empty(tmp_path):
    plan = json.loads(build_plan(batch(1), tmp_path, [], allure=False).read_text())
    assert plan["path_map"] == {}


def test_path_map_reaches_every_plan_of_prepare_jobs(tmp_path):
    expanded, original = Path("/e/features"), Path("/o/features")
    jobs = prepare_jobs([batch(1), batch(2)], tmp_path, [], allure=False, path_map={expanded: original})
    for job in jobs:
        assert json.loads(job.plan_path.read_text())["path_map"] == {str(expanded): str(original)}


def test_plan_permissions_are_owner_only_even_with_a_permissive_umask(tmp_path):
    mask = os.umask(0)
    try:
        plan_path = build_plan(batch(), tmp_path, ["-D", "secret=value"], allure=False)
    finally:
        os.umask(mask)
    plan = json.loads(plan_path.read_text())
    assert stat.S_IMODE(plan_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(plan_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(Path(plan["locations_file"]).stat().st_mode) == 0o600


def test_plan_permissions_reject_an_existing_locations_file_without_overwriting(tmp_path):
    target = tmp_path / "tmp"
    target.mkdir()
    locations = target / "batch-1.locations"
    locations.write_text("keep")
    with pytest.raises(HiveError, match="cannot write private run file"):
        build_plan(batch(), tmp_path, [], allure=False)
    assert locations.read_text() == "keep"


def test_atomic_write_does_not_touch_another_runs_temporary_file(tmp_path):
    other = tmp_path / "report.html.tmp"
    other.write_text("half written by another run", encoding="utf-8")

    write_text_atomically(tmp_path / "report.html", "<html>mine</html>")

    assert (tmp_path / "report.html").read_text(encoding="utf-8") == "<html>mine</html>"
    assert other.read_text(encoding="utf-8") == "half written by another run"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["report.html", "report.html.tmp"]


def test_stale_report_generated_by_behave_hive_is_removed(tmp_path):
    report = tmp_path / "report.html"
    report.write_text(f'<html><head><meta name="generator" content="{REPORT_MARKER}"></head></html>', encoding="utf-8")
    remove_stale_report(report)
    assert not report.exists()


@pytest.mark.parametrize("content", ["<html>mine</html>", "", REPORT_MARKER[::-1]])
def test_file_without_the_marker_is_never_removed(tmp_path, content):
    report = tmp_path / "report.html"
    report.write_text(content, encoding="utf-8")
    remove_stale_report(report)
    assert report.read_text(encoding="utf-8") == content


def test_marker_beyond_the_head_of_the_file_does_not_count(tmp_path):
    report = tmp_path / "notes.html"
    report.write_text("x" * 4096 + REPORT_MARKER, encoding="utf-8")
    remove_stale_report(report)
    assert report.exists()


def test_stale_report_cleanup_ignores_missing_files_directories_and_symlinks(tmp_path):
    remove_stale_report(tmp_path / "missing.html")
    folder = tmp_path / "folder.html"
    folder.mkdir()
    remove_stale_report(folder)
    assert folder.is_dir()
    real = tmp_path / "real.html"
    real.write_text(REPORT_MARKER, encoding="utf-8")
    link = tmp_path / "link.html"
    link.symlink_to(real)
    remove_stale_report(link)
    assert link.is_symlink() and real.exists()


def test_stale_report_cleanup_ignores_unreadable_files(tmp_path):
    report = tmp_path / "report.html"
    report.write_text(REPORT_MARKER, encoding="utf-8")
    report.chmod(0)
    try:
        remove_stale_report(report)
    finally:
        report.chmod(0o600)
    assert report.exists()
