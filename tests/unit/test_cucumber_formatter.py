import base64
import hashlib
import json
import re
import textwrap
from types import SimpleNamespace

import jsonschema
import pytest

from behave_hive.status import scenario_status

FORMATTER = "behave_hive.formatters.cucumber:CucumberJSONFormatter"


@pytest.fixture
def project(make_project):
    return make_project()


def run_json(project, *args, expect=(0, 1)):
    result = project.run("behave", "features", "-f", FORMATTER, "-o", "out.json", *args)
    assert result.returncode in expect, result.stdout + result.stderr
    return json.loads((project.root / "out.json").read_text(encoding="utf-8"))


def scenarios(data):
    return [e for f in data for e in f["elements"] if e["type"] == "scenario"]


def tag_pairs(element):
    return [(t["name"], t["line"]) for t in element["tags"]]


# --- 5.3 structure ---------------------------------------------------------------

BASIC = """\
@web
Feature: Login
  A feature
  with two lines

  Scenario: passes
    Given value "ok"

  Scenario: fails
    Given value "bad"
"""


def test_structure_validates_against_the_schema(project, cucumber_schema):
    project.write("features/login.feature", BASIC)
    data = run_json(project)
    jsonschema.validate(data, cucumber_schema)


def test_structure_feature_fields(project):
    project.write("features/login.feature", BASIC)
    (feature,) = run_json(project)
    assert feature["uri"] == "features/login.feature"
    assert feature["keyword"] == "Feature"
    assert feature["name"] == "Login"
    assert feature["description"] == "A feature\nwith two lines"
    assert feature["line"] == 2
    assert feature["tags"] == [{"name": "@web", "line": 1}]


def test_structure_scenario_fields(project):
    project.write("features/login.feature", BASIC)
    passing, failing = scenarios(run_json(project))
    assert (passing["keyword"], passing["name"], passing["type"], passing["line"]) == (
        "Scenario", "passes", "scenario", 6,
    )
    assert passing["description"] == ""
    assert failing["line"] == 9


def test_structure_failed_step_has_error_message_with_traceback(project):
    project.write("features/login.feature", BASIC)
    _, failing = scenarios(run_json(project))
    step = failing["steps"][0]
    assert step["result"]["status"] == "failed"
    assert "Traceback" in step["result"]["error_message"]
    assert "unexpected value: bad" in step["result"]["error_message"]


def test_structure_file_is_written_atomically(project):
    project.write("features/login.feature", BASIC)
    run_json(project)
    assert not (project.root / "out.json.tmp").exists()


def test_structure_direct_use_on_a_directory_with_tags(project):
    project.write(
        "features/a.feature",
        """\
        Feature: A
          @smoke
          Scenario: tagged
            Given value "ok"
          Scenario: untagged
            Given value "ok"
        """,
    )
    names = [s["name"] for s in scenarios(run_json(project, "--tags=@smoke"))]
    assert names == ["tagged"]


def test_structure_json_is_utf8_without_ascii_escaping(project):
    project.write("features/a.feature", 'Feature: Café\n  Scenario: s\n    Given value "ok"\n')
    raw = (project.root / "out.json")
    run_json(project)
    assert "Café" in raw.read_text(encoding="utf-8")


# --- 5.4 ids and tags ------------------------------------------------------------


def slug(text):
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def test_ids_feature_id_is_slug_plus_sha256_prefix_of_the_uri(project):
    project.write("features/Café Login.feature", BASIC)
    (feature,) = run_json(project)
    uri = feature["uri"]
    assert slug(uri) == "features-cafe-login-feature"
    assert feature["id"] == f"features-cafe-login-feature-{hashlib.sha256(uri.encode()).hexdigest()[:8]}"


def test_ids_same_slug_uris_get_different_feature_ids(project):
    project.write("features/a_b.feature", BASIC)
    project.write("features/a-b.feature", BASIC)
    ids = [f["id"] for f in run_json(project)]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert all(i.startswith("features-a-b-feature-") for i in ids)


def test_ids_scenarios_with_the_same_name_differ_by_line(project):
    project.write(
        "features/a.feature",
        'Feature: F\n\n  Scenario: Login\n    Given value "ok"\n\n  Scenario: Login\n    Given value "ok"\n',
    )
    first, second = scenarios(run_json(project))
    assert first["id"].endswith(";login-l3")
    assert second["id"].endswith(";login-l6")
    assert first["id"].split(";")[0] == run_json(project)[0]["id"]


OUTLINE = """\
@web
Feature: F
  @login
  Scenario Outline: Outline
    Given value "<v>"

    @smoke
    Examples: basics
      | v  |
      | ok |
      | ok |
      | ok |

    Examples: more
      | v  |
      | ok |
      | ok |
"""


def test_ids_outline_rows_are_numbered_across_examples(project):
    project.write("features/a.feature", OUTLINE)
    rows = scenarios(run_json(project))
    assert len(rows) == 5
    assert [r["id"].split(";", 1)[1] for r in rows] == [f"outline-l4;;{n}" for n in range(1, 6)]


def test_ids_outline_row_line_is_the_examples_row_line(project):
    project.write("features/a.feature", OUTLINE)
    assert [r["line"] for r in scenarios(run_json(project))] == [10, 11, 12, 16, 17]


def test_ids_empty_slug_falls_back_to_scenario(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: 日本\n    Given value "ok"\n')
    (scenario,) = scenarios(run_json(project))
    assert scenario["id"].endswith(";scenario-l2")


def test_ids_do_not_depend_on_the_selection_order(project):
    project.write("features/a.feature", OUTLINE)
    full = {r["id"] for r in scenarios(run_json(project))}
    partial = {r["id"] for r in scenarios(run_json(project, "--tags=@smoke"))}
    assert partial <= full


def test_tags_examples_tag_order_and_lines(project):
    project.write("features/a.feature", OUTLINE)
    first = scenarios(run_json(project))[0]
    assert first["tags"] == [
        {"name": "@web", "line": 1},
        {"name": "@login", "line": 3},
        {"name": "@smoke", "line": 7},
    ]
    last = scenarios(run_json(project))[-1]
    assert tag_pairs(last) == [("@web", 1), ("@login", 3)]


def test_tags_include_rule_tags_between_feature_and_scenario(project):
    project.write(
        "features/a.feature",
        """\
        @f
        Feature: F
          @r
          Rule: R
            @s
            Scenario: S
              Given value "ok"
        """,
    )
    (scenario,) = scenarios(run_json(project))
    assert tag_pairs(scenario) == [("@f", 1), ("@r", 3), ("@s", 5)]


def test_tags_each_tag_appears_once_with_its_first_line(project):
    project.write(
        "features/a.feature",
        """\
        @x
        Feature: F
          @x @y
          Scenario: S
            Given value "ok"
        """,
    )
    (scenario,) = scenarios(run_json(project))
    assert tag_pairs(scenario) == [("@x", 1), ("@y", 3)]


def test_tags_parametrized_tag_uses_the_row_value_and_the_template_line(project):
    project.write(
        "features/a.feature",
        """\
        Feature: F
          @case.<v>
          Scenario Outline: O
            Given value "<v>"
            Examples:
              | v  |
              | ok |
        """,
    )
    (row,) = scenarios(run_json(project))
    assert tag_pairs(row) == [("@case.ok", 2)]


def test_tags_special_row_and_examples_parameters(project):
    project.write(
        "features/a.feature",
        """\
        Feature: F
          @row.<row.id> @group.<examples.name>
          Scenario Outline: O
            Given value "<v>"
            Examples: basics
              | v  |
              | ok |
        """,
    )
    (row,) = scenarios(run_json(project))
    assert tag_pairs(row) == [("@row.1.1", 2), ("@group.basics", 2)]


def test_tags_identical_rows_in_two_examples_keep_their_own_examples_tag(project):
    project.write(
        "features/a.feature",
        """\
        Feature: F
          Scenario Outline: O
            Given value "<v>"
            @a
            Examples: one
              | v  |
              | ok |
            @b
            Examples: two
              | v  |
              | ok |
        """,
    )
    first, second = scenarios(run_json(project))
    assert tag_pairs(first) == [("@a", 4)]
    assert tag_pairs(second) == [("@b", 8)]


# --- 5.5 steps and backgrounds ----------------------------------------------------

STEP_DETAILS = """\
Feature: F
  Scenario: details
    Given value "ok"
    Given the table
      | a | b |
      | 1 | 2 |
    Given the text
      \"\"\"json
      {"k": 1}
      \"\"\"
    Given I wait 0.25 seconds
    Given an unknown step
"""

DETAIL_STEPS = """\
from behave import given


@given("the table")
def step_table(context):
    pass


@given("the text")
def step_text(context):
    pass
"""


def test_steps_keyword_has_trailing_space_and_name_and_line(project):
    project.write("features/steps/detail_steps.py", DETAIL_STEPS)
    project.write("features/a.feature", STEP_DETAILS)
    (scenario,) = scenarios(run_json(project))
    first = scenario["steps"][0]
    assert (first["keyword"], first["name"], first["line"]) == ("Given ", 'value "ok"', 3)


def test_steps_match_location_present_for_defined_and_absent_for_undefined(project):
    project.write("features/steps/detail_steps.py", DETAIL_STEPS)
    project.write("features/a.feature", STEP_DETAILS)
    (scenario,) = scenarios(run_json(project))
    steps = scenario["steps"]
    assert re.fullmatch(r".*steps\.py:\d+", steps[0]["match"]["location"])
    assert "match" not in steps[-1]
    assert steps[-1]["result"]["status"] == "undefined"


def test_steps_table_rows_and_docstring(project):
    project.write("features/steps/detail_steps.py", DETAIL_STEPS)
    project.write("features/a.feature", STEP_DETAILS)
    (scenario,) = scenarios(run_json(project))
    table, text = scenario["steps"][1], scenario["steps"][2]
    assert table["rows"] == [{"cells": ["a", "b"]}, {"cells": ["1", "2"]}]
    assert text["doc_string"] == {"value": '{"k": 1}', "content_type": "text/plain", "line": 8}


def test_steps_duration_is_integer_nanoseconds(project):
    project.write("features/steps/detail_steps.py", DETAIL_STEPS)
    project.write("features/a.feature", STEP_DETAILS)
    (scenario,) = scenarios(run_json(project))
    duration = scenario["steps"][3]["result"]["duration"]
    assert isinstance(duration, int)
    assert 200_000_000 <= duration <= 500_000_000


def test_steps_after_an_undefined_step_are_skipped(project):
    project.write(
        "features/a.feature",
        'Feature: F\n  Scenario: s\n    Given an unknown step\n    And value "ok"\n',
    )
    (scenario,) = scenarios(run_json(project))
    assert [s["result"]["status"] for s in scenario["steps"]] == ["undefined", "skipped"]


BACKGROUNDS = """\
Feature: F
  Background: Shared
    Given value "ok"

  Scenario: top level
    Given value "ok"

  Rule: with its own
    Background: Rule bg
      Given value "ok"

    Scenario: first
      Given value "ok"

    Scenario: second
      Given value "ok"

  Rule: without its own
    Scenario: third
      Given value "ok"
"""


def elements(data):
    return data[0]["elements"]


def test_background_feature_and_rule_backgrounds_are_combined_before_each_scenario(project):
    project.write("features/a.feature", BACKGROUNDS)
    elems = elements(run_json(project))
    types = [(e["type"], e["name"]) for e in elems]
    assert types == [
        ("background", "Shared"), ("scenario", "top level"),
        ("background", "Rule bg"), ("scenario", "first"),
        ("background", "Rule bg"), ("scenario", "second"),
        ("background", "Shared"), ("scenario", "third"),
    ]
    rule_bg = elems[2]
    assert len(rule_bg["steps"]) == 2
    assert rule_bg["line"] == 9


def test_background_of_a_rule_without_its_own_uses_the_feature_background_identity(project):
    project.write("features/a.feature", BACKGROUNDS)
    elems = elements(run_json(project))
    bg, third = elems[-2], elems[-1]
    assert (bg["name"], bg["line"]) == ("Shared", 2)
    assert len(bg["steps"]) == 1
    assert third["name"] == "third"


def test_background_scenario_steps_do_not_include_background_steps(project):
    project.write("features/a.feature", BACKGROUNDS)
    elems = elements(run_json(project))
    assert len(elems[1]["steps"]) == 1


# --- 5.6 statuses, hooks and embeddings -------------------------------------------


def step(status):
    return SimpleNamespace(status=SimpleNamespace(name=status))


def scenario_stub(name="passed", hook_failed=False, should_skip=False):
    return SimpleNamespace(
        hook_failed=hook_failed, should_skip=should_skip, status=SimpleNamespace(name=name)
    )


@pytest.mark.parametrize(
    "steps, kwargs, expected",
    [
        (["passed"], {}, "passed"),
        (["passed", "failed", "undefined"], {}, "failed"),
        (["passed", "undefined", "pending"], {}, "undefined"),
        (["passed", "pending"], {}, "pending"),
        (["untested_pending"], {}, "pending"),
        (["pending_warn", "passed"], {}, "passed"),
        (["skipped", "skipped"], {}, "skipped"),
        (["untested"], {}, "skipped"),
        ([], {}, "skipped"),
        (["passed"], {"should_skip": True}, "skipped"),
        (["passed", "passed"], {"hook_failed": True}, "failed"),
        (["passed"], {"name": "cleanup_error"}, "failed"),
        (["undefined"], {"hook_failed": True}, "failed"),
    ],
)
def test_statuses_scenario_status_priority(steps, kwargs, expected):
    assert scenario_status(scenario_stub(**kwargs), [step(s) for s in steps]) == expected


def internal(scenario):
    return scenario["x-behave-hive"]


def test_statuses_undefined_step_makes_the_scenario_undefined(project):
    project.write("features/a.feature", "Feature: F\n  Scenario: s\n    Given an unknown step\n")
    (scenario,) = scenarios(run_json(project))
    assert internal(scenario)["status"] == "undefined"


def test_statuses_failed_takes_priority_over_undefined(project):
    project.write(
        "features/a.feature",
        'Feature: F\n  Scenario: s\n    Given value "bad"\n    And an unknown step\n',
    )
    (scenario,) = scenarios(run_json(project))
    assert internal(scenario)["status"] == "failed"
    assert internal(scenario)["behave_status"] == "failed"


PENDING_STEPS = """\
from behave import given
from behave.exception import StepNotImplementedError


@given("a pending step")
def step_pending(context):
    raise StepNotImplementedError("todo")
"""


def test_statuses_pending_step_is_pending_not_failed(project):
    project.write("features/steps/pending_steps.py", PENDING_STEPS)
    project.write("features/a.feature", "Feature: F\n  Scenario: s\n    Given a pending step\n")
    (scenario,) = scenarios(run_json(project))
    assert scenario["steps"][0]["result"]["status"] == "pending"
    assert internal(scenario)["status"] == "pending"
    assert internal(scenario)["behave_status"] == "error"


def test_statuses_pending_in_a_wip_scenario_leaves_the_scenario_passed(project):
    project.write("features/steps/pending_steps.py", PENDING_STEPS)
    project.write("features/a.feature", "Feature: F\n  @wip\n  Scenario: s\n    Given a pending step\n")
    (scenario,) = scenarios(run_json(project))
    assert scenario["steps"][0]["result"]["status"] == "pending"
    assert internal(scenario)["status"] == "passed"


def test_statuses_real_skip_is_skipped(project):
    project.write("features/environment.py", 'def before_scenario(context, scenario):\n    scenario.skip("by hook")\n')
    project.write("features/a.feature", 'Feature: F\n  @skip\n  Scenario: s\n    Given value "ok"\n')
    (scenario,) = scenarios(run_json(project, "--no-skipped"))
    assert internal(scenario)["status"] == "skipped"
    assert scenario["steps"][0]["result"]["status"] == "skipped"


def test_hooks_cleanup_error_with_passing_steps_is_failed_with_an_after_element(project):
    project.write(
        "features/steps/cleanup_steps.py",
        """\
        from behave import given


        def boom():
            raise RuntimeError("cleanup boom")


        @given("a failing cleanup")
        def step_cleanup(context):
            context.add_cleanup(boom)
        """,
    )
    project.write("features/a.feature", "Feature: F\n  Scenario: s\n    Given a failing cleanup\n")
    (scenario,) = scenarios(run_json(project))
    assert internal(scenario)["status"] == "failed"
    assert internal(scenario)["behave_status"] == "cleanup_error"
    (after,) = scenario["after"]
    assert after["result"]["status"] == "failed"
    assert after["result"]["error_message"]
    assert "before" not in scenario


def test_hooks_error_in_before_scenario_adds_a_before_element(project):
    project.write("features/environment.py", 'def before_scenario(context, scenario):\n    raise RuntimeError("before boom")\n')
    project.write("features/a.feature", 'Feature: F\n  Scenario: s\n    Given value "ok"\n')
    (scenario,) = scenarios(run_json(project))
    assert internal(scenario)["status"] == "failed"
    (before,) = scenario["before"]
    assert before["result"]["status"] == "failed"
    assert "before boom" in before["result"]["error_message"]
    assert "after" not in scenario


def test_hooks_error_in_after_scenario_adds_an_after_element(project):
    project.write("features/environment.py", 'def after_scenario(context, scenario):\n    raise RuntimeError("after boom")\n')
    project.write("features/a.feature", 'Feature: F\n  Scenario: s\n    Given value "ok"\n')
    (scenario,) = scenarios(run_json(project))
    assert internal(scenario)["status"] == "failed"
    (after,) = scenario["after"]
    assert "after boom" in after["result"]["error_message"]
    assert after["match"] == {"location": "environment.py"}


def test_embeddings_attachment_is_added_to_the_step_that_made_it(project):
    project.write("features/a.feature", 'Feature: F\n  Scenario: s\n    Given I attach an image\n    And value "ok"\n')
    (scenario,) = scenarios(run_json(project))
    (embedding,) = scenario["steps"][0]["embeddings"]
    assert embedding["mime_type"] == "image/png"
    assert base64.b64decode(embedding["data"]) == b"\x89PNG\r\n\x1a\nfake"
    assert "embeddings" not in scenario["steps"][1]


def test_embeddings_from_after_scenario_go_to_the_last_step(project):
    project.write(
        "features/environment.py",
        'def after_scenario(context, scenario):\n    context.attach("text/plain", b"late")\n',
    )
    project.write("features/a.feature", 'Feature: F\n  Scenario: s\n    Given value "ok"\n    And value "ok"\n')
    (scenario,) = scenarios(run_json(project))
    assert "embeddings" not in scenario["steps"][0]
    assert base64.b64decode(scenario["steps"][1]["embeddings"][0]["data"]) == b"late"
