import json
import textwrap

import pytest

PROBE = '''
import json
from pathlib import Path

from behave.formatter.base import Formatter

from behave_hive.selection import SelectionSnapshot


class ProbeFormatter(Formatter):
    """Records the lines of the scenarios the snapshot selects, one JSON line per feature."""

    name = "probe"
    description = "records the SelectionSnapshot"

    def feature(self, feature):
        snapshot = SelectionSnapshot(feature, self.config)
        selected = [s.line for s in feature.walk_scenarios() if s in snapshot]
        with Path("selected.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"file": feature.filename, "lines": selected}) + "\\n")
'''

FEATURE = """\
Feature: F
  Scenario Outline: O
    Given value "<v>"

    @smoke
    Examples: a
      | v |
      | ok |
      | ok |
      | ok |

    Examples: b
      | v |
      | ok |

  Scenario: plain
    Given value "ok"

  @skip
  Scenario: skipped by hook
    Given value "ok"
"""

ENVIRONMENT = """\
def before_scenario(context, scenario):
    if "skip" in scenario.tags:
        scenario.skip("by hook")
"""


@pytest.fixture
def project(make_project):
    project = make_project()
    project.write("probe_formatter.py", PROBE)
    project.write("features/environment.py", ENVIRONMENT)
    project.write("features/a.feature", FEATURE)
    return project


def selected(project, *args):
    result = project.run("behave", *args, "-f", "probe_formatter:ProbeFormatter", "--no-summary")
    assert result.returncode in (0, 1), result.stdout + result.stderr
    path = project.root / "selected.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return {r["file"].split("/")[-1]: r["lines"] for r in records}


def test_without_filters_selects_every_scenario_including_a_tagged_skip(project):
    assert selected(project, "features") == {"a.feature": [8, 9, 10, 14, 16, 20]}


def test_two_row_locations_of_a_four_row_outline(project):
    assert selected(project, "features/a.feature:8", "features/a.feature:14") == {"a.feature": [8, 14]}


def test_outline_line_selects_all_its_rows(project):
    assert selected(project, "features/a.feature:2") == {"a.feature": [8, 9, 10, 14]}


def test_directory_with_tags(project):
    assert selected(project, "features", "--tags=@smoke") == {"a.feature": [8, 9, 10]}


def test_real_skip_stays_selected_with_no_skipped(project):
    lines = selected(project, "features", "--no-skipped")["a.feature"]
    assert 20 in lines


def test_name_filter(project):
    assert selected(project, "features", "-n", "plain") == {"a.feature": [16]}


def test_feature_without_selected_scenarios(project):
    assert selected(project, "features", "--tags=@nonexistent").get("a.feature", []) == []
