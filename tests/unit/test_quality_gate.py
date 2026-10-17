"""Exercise real quality tools against deliberate regressions, outside the source tree."""

import json
import os
import subprocess
import sys
from pathlib import Path

from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "pyproject.toml"


def test_ruff_rejects_complexity_and_shell_execution(tmp_path):
    module = tmp_path / "regression.py"
    branches = "".join(f"    if value == {n}:\n        return {n}\n" for n in range(10))
    module.write_text(
        "import subprocess\n\ndef complex_function(value):\n" + branches
        + '\ndef risky(command):\n    subprocess.run(command, shell=True)\n', encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--config", str(CONFIG), str(module)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "C901" in result.stdout and "complex_function" in result.stdout
    assert "S602" in result.stdout


def test_duplicate_gate_names_both_modules(tmp_path):
    block = """def duplicated(values):
    result = []
    for value in values:
        normalized = str(value).strip()
        result.append(normalized.lower())
    result.sort()
    return tuple(result)
"""
    modules = [tmp_path / "first.py", tmp_path / "second.py"]
    for module in modules:
        module.write_text(block, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pylint", "--rcfile", str(CONFIG), *(str(p) for p in modules)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "duplicate-code" in result.stdout
    assert "first" in result.stdout and "second" in result.stdout


def test_coverage_measures_worker_subprocess(make_project, tmp_path):
    project = make_project()
    project.write("features/a.feature", 'Feature: F\n  Scenario: S\n    Given value "ok"\n')
    locations = project.write("locations.txt", "features/a.feature\n")
    plan = project.write("plan.json", json.dumps({
        "locations_file": str(locations), "behave_args": [],
        "cucumber_out": str(project.root / "result.json"), "allure_dir": None,
    }))
    data_file = tmp_path / "worker-coverage"
    # A fresh coverage process launches the worker; only the subprocess patch can measure it.
    launcher = project.write(
        "launch.py", "import subprocess, sys\nsubprocess.run(sys.argv[1:], check=True)\n"
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "coverage", "run", "--rcfile", str(CONFIG), str(launcher),
            sys.executable, "-m", "behave_hive.worker",
            "--plan", str(plan),
        ],
        cwd=project.root, capture_output=True, text=True, check=False,
        env={**os.environ, "COVERAGE_FILE": str(data_file)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    files = list(tmp_path.glob("worker-coverage*"))
    assert files
    measured = set()
    for path in files:
        data = CoverageData(basename=str(path))
        data.read()
        measured.update(data.measured_files())
    assert any(path.endswith("behave_hive/worker.py") for path in measured)
