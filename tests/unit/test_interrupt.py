import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from behave_hive.batching import Batch
from behave_hive.discovery import Unit
from behave_hive.runner import execute_batches, prepare_jobs


def test_finished_process_is_not_signalled_during_interrupt(tmp_path):
    jobs = prepare_jobs([Batch(1, Path("/proj/features"), (Unit(Path("/proj/features/a.feature"), 3),))],
                        tmp_path, [], allure=False)
    started, release = threading.Event(), threading.Event()
    killed = []

    class Finished:
        pid = 4242

        def wait(self):
            assert release.wait(10)
            return 0

        def poll(self):
            release.set()
            return 0

    def launch(*args, **kwargs):
        started.set()
        return Finished()

    def interrupted(futures):
        assert started.wait(10)
        raise KeyboardInterrupt

    result = execute_batches(jobs, 1, cwd=tmp_path, popen=launch, wait=interrupted,
                             kill_group=lambda pid, sig: killed.append((pid, sig)), echo=lambda line: None)
    assert result.interrupted
    assert killed == []


def test_sigint_before_a_pending_task_launches_prevents_the_launch_and_kills_running_processes(tmp_path):
    batches = [Batch(i, Path("/proj/features"), (Unit(Path("/proj/features/a.feature"), 10 + i),)) for i in (1, 2)]
    jobs = prepare_jobs(batches, tmp_path, [], allure=False)

    started = threading.Event()
    at_barrier = threading.Event()
    release = threading.Event()
    killed = threading.Event()
    popen_calls: list[int] = []
    kills: list[tuple[int, int]] = []
    arrivals = iter(range(1, 100))
    arrivals_lock = threading.Lock()

    class Proc:
        def __init__(self, pid):
            self.pid = pid

        def wait(self, timeout=None):
            killed.wait(10)
            return -15

        def poll(self):
            return -15 if killed.is_set() else None

    def fake_popen(command, **kwargs):
        popen_calls.append(len(popen_calls) + 1)
        started.set()
        return Proc(4242)

    def before_launch():
        with arrivals_lock:
            arrival = next(arrivals)
        if arrival == 2:  # the second task stops right before entering launch_lock
            at_barrier.set()
            assert release.wait(10)

    def fake_wait(futures):
        assert started.wait(10) and at_barrier.wait(10)
        raise KeyboardInterrupt

    def fake_kill(pid, sig):
        kills.append((pid, sig))
        release.set()  # the pending task proceeds only after cancel was set
        killed.set()

    result = execute_batches(
        jobs, 2, cwd=tmp_path, popen=fake_popen, echo=lambda line: None,
        before_launch=before_launch, wait=fake_wait, kill_group=fake_kill, grace=0.2,
    )

    assert result.interrupted is True
    assert popen_calls == [1], "the pending task must not call popen after the interrupt"
    assert kills == [(4242, signal.SIGTERM)]
    assert result.partials == []
    assert result.batch_errors == []


def test_sigint_escalates_to_sigkill_when_a_process_ignores_sigterm(tmp_path):
    batches = [Batch(1, Path("/proj/features"), (Unit(Path("/proj/features/a.feature"), 10),))]
    jobs = prepare_jobs(batches, tmp_path, [], allure=False)
    started = threading.Event()
    dead = threading.Event()
    kills: list[int] = []

    class Stubborn:
        pid = 777

        def wait(self, timeout=None):
            dead.wait(10)
            return -9

        def poll(self):
            return -9 if dead.is_set() else None

    def fake_wait(futures):
        assert started.wait(10)
        raise KeyboardInterrupt

    def fake_kill(pid, sig):
        kills.append(sig)
        if sig == signal.SIGKILL:
            dead.set()

    def fake_popen(command, **kwargs):
        started.set()
        return Stubborn()

    execute_batches(jobs, 1, cwd=tmp_path, popen=fake_popen, echo=lambda line: None,
                    wait=fake_wait, kill_group=fake_kill, grace=0.2)
    assert kills == [signal.SIGTERM, signal.SIGKILL]


SLOW_STEPS = '''
import os, time
from pathlib import Path
from behave import given


@given('row "{n:d}"')
def step_row(context, n):
    if n % 2 == 0:
        pids = Path(os.getcwd()) / "pids"
        pids.mkdir(exist_ok=True)
        (pids / str(os.getpid())).write_text(str(os.getpid()))
        time.sleep(30)
'''

FEATURE = """\
Feature: Slow
  Scenario Outline: Row
    Given row "<n>"

    Examples:
      | n |
      | 1 |
      | 2 |
      | 3 |
      | 4 |
      | 5 |
      | 6 |
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigint_integration_stops_everything_and_reports_only_complete_batches(make_project):
    project = make_project()
    project.write("features/steps/slow_steps.py", SLOW_STEPS)
    project.write("features/slow.feature", FEATURE)
    proc = subprocess.Popen(
        [sys.executable, "-m", "behave_hive.cli", "run", "--parallel", "-w", "2", "--chunk", "2",
         "--formats", "allure,cucumber"],
        cwd=project.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    pids_dir = project.root / "pids"
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and len(list(pids_dir.glob("*"))) < 2:
            time.sleep(0.05)
        assert len(list(pids_dir.glob("*"))) == 2, "both slow scenarios should have started"
        proc.send_signal(signal.SIGINT)
        output, _ = proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 130, output
    pids = [int(p.name) for p in pids_dir.glob("*")]
    assert len(pids) <= 2
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    reports = project.root / "reports"
    cucumber = reports / "cucumber.json"
    data = json.loads(cucumber.read_text()) if cucumber.exists() else []
    assert [e for f in data for e in f["elements"]] == []
    assert not list((reports / "allure-results").glob("*-result.json"))
