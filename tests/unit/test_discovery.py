from pathlib import Path

import pytest

from behave_hive.discovery import Unit, discover_units
from behave_hive.errors import ConfigError

I18N = Path(__file__).parent.parent / "fixtures" / "i18n"

OUTLINE = """\
Feature: F
  Scenario Outline: O
    Given value "<v>"

    @smoke
    Examples: smoke
      | v |
      | 1 |
      | 2 |
      | 3 |

    Examples: other
      | v |
      | 4 |
      | 5 |

  Scenario: plain
    Given value "ok"

  Rule: R
    Scenario: in rule
      Given value "ok"
"""


def discover(inputs, args=(), scheme="scenario", parallel=True):
    return discover_units(
        [Path(i) for i in inputs], list(args), scheme=scheme, parallel=parallel
    )


# --- 4.1 units ------------------------------------------------------------------


def test_units_scenario_scheme_has_one_unit_per_row_and_rule_scenario(project):
    feature = project.write("features/a.feature", OUTLINE).resolve()
    units = discover([feature])
    assert units == [Unit(feature, line) for line in (8, 9, 10, 14, 15, 17, 21)]


def test_units_are_sorted_by_path_and_line(project):
    b = project.write("features/b.feature", OUTLINE).resolve()
    a = project.write("features/a.feature", OUTLINE).resolve()
    units = discover([b, a])
    assert [u.path for u in units] == [a] * 7 + [b] * 7
    assert [u.line for u in units[:7]] == sorted(u.line for u in units[:7])


def test_units_feature_scheme_has_one_unit_per_feature(project):
    a = project.write("features/a.feature", OUTLINE).resolve()
    b = project.write("features/b.feature", OUTLINE).resolve()
    assert discover([a, b], scheme="feature") == [Unit(a, None), Unit(b, None)]


def test_units_sequential_mode_uses_feature_units_even_with_scenario_scheme(project):
    a = project.write("features/a.feature", OUTLINE).resolve()
    assert discover([a], scheme="scenario", parallel=False) == [Unit(a, None)]


def test_units_directory_input_finds_nested_features(project):
    nested = project.write("features/auth/login.feature", OUTLINE).resolve()
    top = project.write("features/top.feature", OUTLINE).resolve()
    units = discover([project.features], scheme="feature")
    assert units == [Unit(nested, None), Unit(top, None)]


def test_units_overlapping_inputs_are_deduplicated(project):
    a = project.write("features/a.feature", OUTLINE).resolve()
    units = discover([project.features, a])
    assert len(units) == 7
    assert len(set(units)) == 7


def test_units_csv_rows_become_units_without_a_copy_of_the_feature(project):
    project.write("features/data/v.csv", "v\n1\n2\n3\n4\n5\n")
    text = "Feature: F\n  Scenario Outline: O\n    Given value \"<v>\"\n    Examples:\n      | read('data/v.csv') |\n"
    feature = project.write("features/a.feature", text).resolve()
    assert len(discover([feature])) == 5
    assert feature.read_text(encoding="utf-8") == text


def test_units_reject_incompatible_behave_configuration(project):
    a = project.write("features/a.feature", OUTLINE)
    with pytest.raises(ConfigError, match="wip"):
        discover([a], args=["--wip"])


# --- 4.2 filter and effective configuration -------------------------------------


@pytest.mark.parametrize("args", [["--tags=@smoke"], ["--tags", "@smoke"], ["-t", "@smoke"], ["-t@smoke"]])
def test_effective_tag_forms_select_the_tagged_examples(project, args):
    a = project.write("features/a.feature", OUTLINE).resolve()
    assert discover([a], args=args) == [Unit(a, line) for line in (8, 9, 10)]


def test_effective_default_tags_from_behave_ini(project):
    text = (
        "Feature: F\n"
        "  Scenario: one\n    Given value \"ok\"\n"
        "  @wip\n  Scenario: two\n    Given value \"ok\"\n"
        "  Scenario: three\n    Given value \"ok\"\n"
    )
    a = project.write("features/a.feature", text)
    project.write("behave.ini", "[behave]\ndefault_tags = not @wip\n")
    assert len(discover([a])) == 2


def test_effective_tags_argument_overrides_default_tags(project):
    text = (
        "Feature: F\n"
        "  @expected_fail\n  Scenario: one\n    Given value \"ok\"\n"
        "  Scenario: two\n    Given value \"ok\"\n"
    )
    a = project.write("features/a.feature", text).resolve()
    project.write("behave.ini", "[behave]\ndefault_tags = not @expected_fail\n")
    assert discover([a], args=["--tags=@expected_fail"]) == [Unit(a, 3)]


def test_effective_config_tags_placeholder(project):
    text = (
        "Feature: F\n"
        "  @smoke\n  Scenario: one\n    Given value \"ok\"\n"
        "  @smoke @slow\n  Scenario: two\n    Given value \"ok\"\n"
        "  @slow\n  Scenario: three\n    Given value \"ok\"\n"
    )
    a = project.write("features/a.feature", text).resolve()
    project.write("behave.ini", "[behave]\ndefault_tags = not @slow\n")
    assert discover([a], args=["--tags=@smoke and {config.tags}"]) == [Unit(a, 3)]


def test_effective_language_from_configuration_without_directive(project):
    path = project.write("features/es.feature", (I18N / "es_lang.feature").read_text(encoding="utf-8")).resolve()
    project.write("behave.ini", "[behave]\nlang = es\n")
    assert discover([path]) == [Unit(path, 2), Unit(path, 5)]


def test_effective_feature_without_matching_scenarios_is_discarded(project):
    a = project.write("features/a.feature", OUTLINE)
    assert discover([a], args=["--tags=@nonexistent"], scheme="feature") == []
    assert discover([a], args=["--tags=@nonexistent"]) == []


# --- 4.3 @setup / @teardown -----------------------------------------------------

SETUP = """\
Feature: F
  @setup
  Scenario: prepare
    Given value "ok"

  Scenario: test
    Given value "ok"
"""


@pytest.mark.parametrize("tag", ["setup", "teardown"])
def test_setup_teardown_parallel_scenario_scheme_is_rejected(project, tag):
    a = project.write("features/a.feature", SETUP.replace("@setup", f"@{tag}"))
    with pytest.raises(ConfigError) as exc:
        discover([a], scheme="scenario", parallel=True)
    assert "a.feature" in str(exc.value)
    assert "scheme = feature" in str(exc.value)


def test_setup_teardown_accepted_in_sequential_mode(project):
    a = project.write("features/a.feature", SETUP).resolve()
    assert discover([a], scheme="scenario", parallel=False) == [Unit(a, None)]


def test_setup_teardown_accepted_with_feature_scheme(project):
    a = project.write("features/a.feature", SETUP).resolve()
    assert discover([a], scheme="feature", parallel=True) == [Unit(a, None)]


def test_setup_teardown_in_a_feature_that_does_not_run_is_ignored(project):
    a = project.write("features/a.feature", SETUP.replace("Scenario: test", "@other\n  Scenario: test"))
    b = project.write("features/b.feature", OUTLINE).resolve()
    assert len(discover([a, b], args=["--tags=@smoke"], scheme="scenario", parallel=True)) == 3


# --- name and include/exclude filters ---------------------------------------------

NAMES = """\
Feature: F
  Scenario: Login with a locked user
    Given value "ok"

  Scenario: Login with a valid user
    Given value "ok"

  Scenario Outline: Login as <role>
    Given value "<role>"

    Examples:
      | role  |
      | admin |
      | guest |
"""


def test_name_filter_keeps_only_matching_scenarios(project):
    a = project.write("features/a.feature", NAMES).resolve()
    assert discover([a], args=["--name", "locked user"]) == [Unit(a, 2)]


def test_name_filter_picks_one_outline_row(project):
    a = project.write("features/a.feature", NAMES).resolve()
    assert discover([a], args=["-n", "Login as admin"]) == [Unit(a, 13)]


def test_name_filter_accepts_the_equals_form_and_matches_several(project):
    a = project.write("features/a.feature", NAMES).resolve()
    assert discover([a], args=["--name=valid|locked"]) == [Unit(a, 2), Unit(a, 5)]


def test_name_filter_with_feature_scheme_keeps_features_with_a_match(project):
    a = project.write("features/a.feature", NAMES).resolve()
    b = project.write("features/b.feature", OUTLINE).resolve()
    assert discover([a, b], args=["--name", "locked user"], scheme="feature") == [Unit(a, None)]


def test_name_filter_in_sequential_mode_keeps_the_feature_unit(project):
    a = project.write("features/a.feature", NAMES).resolve()
    assert discover([a], args=["--name", "locked user"], parallel=False) == [Unit(a, None)]


def test_name_filter_without_matches_gives_no_units(project):
    a = project.write("features/a.feature", NAMES).resolve()
    assert discover([a], args=["--name", "does not exist"]) == []


def test_name_filter_combines_with_tags(project):
    a = project.write("features/a.feature", OUTLINE).resolve()
    assert discover([a], args=["--tags=@smoke", "--name", "plain"]) == []
    assert len(discover([a], args=["--tags=@smoke", "--name", "O"])) == 3


def test_name_filter_from_behave_ini(project):
    a = project.write("features/a.feature", NAMES).resolve()
    (project.root / "behave.ini").write_text("[behave]\nname = locked user\n")
    assert discover([a]) == [Unit(a, 2)]


def test_include_and_exclude_filter_feature_files(project):
    login = project.write("features/login.feature", NAMES).resolve()
    project.write("features/login_slow.feature", NAMES)
    project.write("features/cart.feature", NAMES)
    units = discover([project.features], args=["--include", r"login\.feature|login_slow", "--exclude", "slow"],
                     scheme="feature")
    assert units == [Unit(login, None)]


def test_include_keeps_only_matching_files(project):
    project.write("features/login.feature", NAMES)
    cart = project.write("features/cart.feature", NAMES).resolve()
    assert discover([project.features], args=["-i", r"cart\.feature"], scheme="feature") == [Unit(cart, None)]


def test_exclude_everything_gives_no_units(project):
    project.write("features/a.feature", NAMES)
    assert discover([project.features], args=["-e", r"a\.feature"]) == []


def test_setup_teardown_guard_still_applies_with_a_name_filter(project):
    a = project.write("features/a.feature", SETUP)
    with pytest.raises(ConfigError, match="scheme = feature"):
        discover([a], args=["--name", "test"], scheme="scenario", parallel=True)


def test_file_patterns_are_matched_against_the_feature_path_even_with_scenario_units(project):
    a = project.write("features/a.feature", NAMES).resolve()
    project.write("features/b.feature", NAMES)
    units = discover([project.features], args=["--include", r"a\.feature$"])
    assert units and {u.path for u in units} == {a}
    assert all(u.line is not None for u in units)
    assert discover([project.features], args=["--exclude", r"\.feature$"]) == []
