
import pytest

from behave_hive.errors import HiveError
from behave_hive.roots import find_root, group_by_root


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
