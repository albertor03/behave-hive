from behave_hive.expand import expand_feature_text

STEPS = '''
from pathlib import Path
from behave import given


@given('the value is "{v}"')
def step_value(context, v):
    with Path("seen.txt").open("a", encoding="utf-8") as f:
        f.write(v + "\\n")
'''

FEATURE = """\
Feature: CSV
  Scenario Outline: uses a row
    Given the value is "<v>"

    Examples:
      | read('data/values.csv') |
"""


def test_expanded_feature_runs_one_scenario_per_row_and_keeps_the_pipe(make_project):
    project = make_project()
    project.write("features/steps/csv_steps.py", STEPS)
    project.write("features/data/values.csv", "v\nx\ny\na|b\n")
    feature = project.write("features/csv.feature", FEATURE)

    feature.write_text(expand_feature_text(FEATURE, feature, "en").text, encoding="utf-8")
    result = project.run("behave", "features/csv.feature")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "3 scenarios passed" in result.stdout
    seen = (project.root / "seen.txt").read_text(encoding="utf-8").splitlines()
    assert seen == ["x", "y", "a|b"]


def test_docstring_with_apparent_csv_reference_reaches_the_step_intact(make_project):
    project = make_project()
    project.write(
        "features/steps/doc_steps.py",
        '''
        from behave import given


        @given("the text is")
        def step_text(context):
            assert context.text == "Examples:\\n| data/login.csv |", repr(context.text)
        ''',
    )
    text = (
        "Feature: Doc\n"
        "  Scenario: docstring\n"
        "    Given the text is\n"
        '      """\n'
        "      Examples:\n"
        "      | data/login.csv |\n"
        '      """\n'
    )
    feature = project.write("features/doc.feature", text)

    expanded = expand_feature_text(text, feature, "en").text
    assert expanded == text
    feature.write_text(expanded, encoding="utf-8")
    result = project.run("behave", "features/doc.feature")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 scenario passed" in result.stdout
