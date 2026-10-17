import pytest

from behave_hive.errors import HiveError
from behave_hive.roots import PathMap, find_root, group_by_root, needs_expansion


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "features"
    (root / "steps").mkdir(parents=True)
    (root / "auth").mkdir()
    (root / "auth" / "login.feature").write_text("Feature: F\n")
    (root / "other.feature").write_text("Feature: G\n")
    return root


def test_find_root_from_a_nested_file(tree):
    assert find_root(tree / "auth" / "login.feature") == tree.resolve()


def test_find_root_from_a_nested_directory(tree):
    assert find_root(tree / "auth") == tree.resolve()


def test_find_root_of_the_root_itself(tree):
    assert find_root(tree) == tree.resolve()


def test_find_root_without_steps_directory_raises(tmp_path):
    (tmp_path / "loose").mkdir()
    (tmp_path / "loose" / "a.feature").write_text("Feature: F\n")
    with pytest.raises(HiveError, match="steps"):
        find_root(tmp_path / "loose" / "a.feature")


def test_group_by_root_groups_inputs_preserving_order(tree, tmp_path):
    other = tmp_path / "more"
    (other / "steps").mkdir(parents=True)
    (other / "b.feature").write_text("Feature: B\n")
    inputs = [tree / "other.feature", other / "b.feature", tree / "auth"]
    grouped = group_by_root(inputs)
    assert list(grouped) == [tree.resolve(), other.resolve()]
    assert grouped[tree.resolve()] == [(tree / "other.feature").resolve(), (tree / "auth").resolve()]


def test_needs_expansion_false_without_csv_examples(tree):
    (tree / "auth" / "login.feature").write_text(
        "Feature: F\n  Scenario Outline: S\n    Given x\n    Examples:\n      | a |\n      | 1 |\n"
    )
    assert needs_expansion(tree, "en") is False


def test_needs_expansion_true_with_a_csv_reference(tree):
    (tree / "auth" / "login.feature").write_text(
        "Feature: F\n  Scenario Outline: S\n    Given x\n    Examples:\n      | read('a.csv') |\n"
    )
    assert needs_expansion(tree, "en") is True


def test_needs_expansion_ignores_csv_lookalike_in_docstring(tree):
    (tree / "other.feature").write_text(
        'Feature: F\n  Scenario: S\n    Given x\n      """\n      Examples:\n      | a.csv |\n      """\n'
    )
    assert needs_expansion(tree, "en") is False


def test_needs_expansion_uses_the_given_language(tree):
    (tree / "other.feature").write_text("Feature: F\n    Ejemplos:\n      | a.csv |\n")
    assert needs_expansion(tree, "en") is False
    assert needs_expansion(tree, "es") is True


def test_path_map_translates_both_ways(tmp_path):
    original, expanded = tmp_path / "features", tmp_path / "work" / "features"
    pm = PathMap({expanded: original})
    assert pm.to_original(expanded / "a" / "x.feature") == original / "a" / "x.feature"
    assert pm.to_expanded(original / "a" / "x.feature") == expanded / "a" / "x.feature"
    assert pm.to_original(expanded) == original


def test_path_map_translates_strings_with_a_line_suffix(tmp_path):
    original, expanded = tmp_path / "features", tmp_path / "work" / "features"
    pm = PathMap({expanded: original})
    assert pm.to_original(f"{expanded}/steps/s.py:12") == f"{original}/steps/s.py:12"


def test_path_map_leaves_unrelated_paths_and_sibling_prefixes_alone(tmp_path):
    original, expanded = tmp_path / "features", tmp_path / "work" / "features"
    pm = PathMap({expanded: original})
    sibling = tmp_path / "work" / "features-extra" / "x.feature"
    assert pm.to_original(sibling) == sibling
    assert pm.to_original("/elsewhere/x.feature") == "/elsewhere/x.feature"
