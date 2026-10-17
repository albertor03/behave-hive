import os

import pytest

from behave_hive.errors import HiveError
from behave_hive.expand import EXPANDED_MARKER, expand_tree

FEATURE = "Feature: F\r\n  Scenario Outline: S\r\n    Given x\r\n    Examples:\r\n      | data/v.csv |\r\n"


@pytest.fixture
def src(tmp_path):
    root = tmp_path / "features"
    (root / "steps").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"x")
    (root / "steps" / "steps.py").write_text("# steps\n")
    (root / "environment.py").write_text("# env\n")
    (root / "data" / "v.csv").write_text("v\n1\n2\n")
    with open(root / "a.feature", "w", newline="") as f:
        f.write(FEATURE)
    return root


def test_tree_expands_features_and_links_everything_else_with_absolute_symlinks(src, tmp_path):
    dst = tmp_path / "out"
    result = expand_tree(src, dst, "en")

    expanded = (dst / "a.feature").read_bytes().decode()
    assert expanded.endswith("      | v |\r\n      | 1 |\r\n      | 2 |\r\n")
    for rel in ["steps/steps.py", "environment.py", "data/v.csv"]:
        link = dst / rel
        assert link.is_symlink()
        assert os.readlink(link) == str((src / rel).resolve())
    assert (dst / "steps").is_dir() and not (dst / "steps").is_symlink()
    assert list(result.sources_by_file) == [dst.resolve() / "a.feature"]
    assert len(result.sources_by_file[dst.resolve() / "a.feature"]) == 2


def test_tree_linked_step_resolves_to_the_original(src, tmp_path):
    dst = tmp_path / "out"
    expand_tree(src, dst, "en")
    assert (dst / "steps" / "steps.py").resolve() == (src / "steps" / "steps.py").resolve()


def test_tree_writes_marker_and_excludes_pycache(src, tmp_path):
    dst = tmp_path / "out"
    expand_tree(src, dst, "en")
    assert (dst / EXPANDED_MARKER).is_file()
    assert not (dst / "__pycache__").exists()


def test_tree_reexpansion_removes_stale_files(src, tmp_path):
    dst = tmp_path / "out"
    expand_tree(src, dst, "en")
    (dst / "stale.txt").write_text("old")
    expand_tree(src, dst, "en")
    assert not (dst / "stale.txt").exists()
    assert (dst / "a.feature").is_file()


def test_tree_destination_inside_source_is_excluded(src):
    dst = src / ".behave-hive" / "run-1"
    expand_tree(src, dst, "en")
    expand_tree(src, dst, "en")
    assert not (dst / ".behave-hive").exists()
    assert (dst / "a.feature").is_file()


def test_tree_accepts_empty_existing_destination(src, tmp_path):
    dst = tmp_path / "out"
    dst.mkdir()
    expand_tree(src, dst, "en")
    assert (dst / "a.feature").is_file()


def test_tree_rejects_destination_equal_to_source_without_deleting(src):
    with pytest.raises(HiveError):
        expand_tree(src, src, "en")
    assert (src / "a.feature").read_bytes().decode() == FEATURE


def test_tree_rejects_destination_that_is_an_ancestor_without_deleting(src):
    with pytest.raises(HiveError):
        expand_tree(src, src.parent, "en")
    assert (src / "a.feature").is_file()


def test_tree_rejects_symlink_destination_without_deleting(src, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "keep.txt").write_text("keep")
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(HiveError):
        expand_tree(src, link, "en")
    assert (real / "keep.txt").read_text() == "keep"


def test_tree_rejects_non_empty_destination_without_marker_without_deleting(src, tmp_path):
    dst = tmp_path / "out"
    dst.mkdir()
    (dst / "precious.txt").write_text("keep")
    with pytest.raises(HiveError):
        expand_tree(src, dst, "en")
    assert (dst / "precious.txt").read_text() == "keep"
