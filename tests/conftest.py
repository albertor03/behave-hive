"""Shared fixtures.

`make_project` creates a minimal behave project (no browser) in `tmp_path` for
fast integration tests. Steps available in the generated project:

    Given value "<v>"           -> passes if v == "ok", fails otherwise
    Given I wait <s> seconds    -> time.sleep(s)
    Given I attach an image     -> context.attach("image/png", PNG_BYTES)
    Given I record my pid       -> writes os.getpid() to <project>/pids/<pid>
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"

STEPS = f'''
import os, time
from pathlib import Path
from behave import given

PNG_BYTES = {PNG_BYTES!r}


@given('value "{{v}}"')
def step_value(context, v):
    assert v == "ok", f"unexpected value: {{v}}"


@given("I wait {{s:f}} seconds")
def step_wait(context, s):
    time.sleep(s)


@given("I attach an image")
def step_attach(context):
    context.attach("image/png", PNG_BYTES)


@given("I record my pid")
def step_pid(context):
    d = Path(os.getcwd()) / "pids"
    d.mkdir(exist_ok=True)
    (d / str(os.getpid())).write_text(str(os.getpid()))
'''


class Project:
    """Temporary behave project. Every path is relative to `root`."""

    def __init__(self, root: Path):
        self.root = root
        self.features = root / "features"
        (self.features / "steps").mkdir(parents=True)
        (self.features / "steps" / "steps.py").write_text(STEPS, encoding="utf-8")

    def write(self, rel: str, content: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
        return path

    def run(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        """Run `python -m <args>` with cwd = root (e.g. run("behave", "features"))."""
        return subprocess.run(
            [sys.executable, "-m", *args],
            cwd=self.root, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )


@pytest.fixture
def make_project(tmp_path, monkeypatch):
    """Return a function that creates a `Project` and chdirs into its root."""

    def _make(name: str = "proj") -> Project:
        project = Project(tmp_path / name)
        monkeypatch.chdir(project.root)
        return project

    return _make


@pytest.fixture
def cucumber_schema():
    import json
    return json.loads((Path(__file__).parent / "schemas" / "cucumber.schema.json").read_text())


@pytest.fixture
def project(make_project):
    """A fresh behave project; modules needing seeded files override this fixture."""
    return make_project()
