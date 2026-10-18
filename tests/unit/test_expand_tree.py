import pytest

from behave_hive import cli, expand
from behave_hive.errors import HiveError
from behave_hive.expand import EXPANDED_MARKER, expand_features

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
    with open(root / "a.feature", "w", encoding="utf-8", newline="") as f:
        f.write(FEATURE)
    return root


def test_expands_the_features_and_writes_nothing_else(src, tmp_path):
    dst = tmp_path / "out"
    expand_features(src, dst, "en")

    expanded = (dst / "a.feature").read_bytes().decode()
    assert expanded.endswith("      | v |\r\n      | 1 |\r\n      | 2 |\r\n")
    assert sorted(p.name for p in dst.rglob("*") if p.is_file()) == [EXPANDED_MARKER, "a.feature"]
    assert [p for p in dst.rglob("*") if p.is_symlink()] == []


def test_expands_nested_features_keeping_their_relative_paths(src, tmp_path):
    (src / "auth").mkdir()
    (src / "auth" / "data").mkdir()
    (src / "auth" / "data" / "v.csv").write_text("v\n9\n")
    (src / "auth" / "b.feature").write_text(FEATURE)
    dst = tmp_path / "out"
    expand_features(src, dst, "en")
    assert "| 9 |" in (dst / "auth" / "b.feature").read_text()


def test_writes_marker_and_excludes_pycache(src, tmp_path):
    dst = tmp_path / "out"
    expand_features(src, dst, "en")
    assert (dst / EXPANDED_MARKER).is_file()
    assert not (dst / "__pycache__").exists()


def test_reexpansion_removes_stale_files(src, tmp_path):
    dst = tmp_path / "out"
    expand_features(src, dst, "en")
    (dst / "stale.txt").write_text("old")
    expand_features(src, dst, "en")
    assert not (dst / "stale.txt").exists()
    assert (dst / "a.feature").is_file()


def test_destination_inside_source_is_excluded(src):
    dst = src / ".behave-hive" / "run-1"
    expand_features(src, dst, "en")
    expand_features(src, dst, "en")
    assert not (dst / ".behave-hive").exists()
    assert (dst / "a.feature").is_file()


def test_accepts_empty_existing_destination(src, tmp_path):
    dst = tmp_path / "out"
    dst.mkdir()
    expand_features(src, dst, "en")
    assert (dst / "a.feature").is_file()


def test_rejects_destination_equal_to_source_without_deleting(src):
    with pytest.raises(HiveError):
        expand_features(src, src, "en")
    assert (src / "a.feature").read_bytes().decode() == FEATURE


def test_rejects_destination_that_is_an_ancestor_without_deleting(src):
    with pytest.raises(HiveError):
        expand_features(src, src.parent, "en")
    assert (src / "a.feature").is_file()


def test_rejects_symlink_destination_without_deleting(src, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "keep.txt").write_text("keep")
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(HiveError):
        expand_features(src, link, "en")
    assert (real / "keep.txt").read_text() == "keep"


def test_rejects_non_empty_destination_without_marker_without_deleting(src, tmp_path):
    dst = tmp_path / "out"
    dst.mkdir()
    (dst / "precious.txt").write_text("keep")
    with pytest.raises(HiveError):
        expand_features(src, dst, "en")
    assert (dst / "precious.txt").read_text() == "keep"


def test_rejects_regular_file_destination_without_deleting(src, tmp_path):
    dst = tmp_path / "precious.txt"
    dst.write_text("keep")
    with pytest.raises(HiveError, match="expansion destination is not a directory"):
        expand_features(src, dst, "en")
    assert dst.read_text() == "keep"
    assert (src / "a.feature").read_bytes().decode() == FEATURE


@pytest.mark.parametrize("replacement", ["symlink", "missing-marker"])
def test_swapped_destination_after_validation_is_rejected_without_deleting(src, tmp_path, monkeypatch, replacement):
    dst, victim = tmp_path / "out", tmp_path / "victim"
    dst.mkdir()
    victim.mkdir()
    (victim / "precious.txt").write_text("keep")
    (dst / EXPANDED_MARKER).write_text("")
    validate = expand._validate_destination
    calls = []

    def swap(source, target):
        validate(source, target)
        calls.append(target)
        if len(calls) == 1:
            (dst / EXPANDED_MARKER).unlink()
            if replacement == "symlink":
                dst.rmdir()
                dst.symlink_to(victim)
            else:
                (dst / "precious.txt").write_text("keep")

    monkeypatch.setattr(expand, "_validate_destination", swap)
    assert cli.main(["expand", str(src), str(dst)]) == 2
    assert (victim / "precious.txt").read_text() == "keep"
    assert (dst / "precious.txt").read_text() == "keep"
    assert (src / "a.feature").read_bytes().decode() == FEATURE


def test_swapped_destination_before_marker_creation_is_rejected(src, tmp_path, monkeypatch):
    dst, victim = tmp_path / "out", tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("keep")
    mkdir = type(dst).mkdir

    def swap(path, *args, **kwargs):
        mkdir(path, *args, **kwargs)
        if path == dst:
            path.rmdir()
            path.symlink_to(victim)

    monkeypatch.setattr(type(dst), "mkdir", swap)
    assert cli.main(["expand", str(src), str(dst)]) == 2
    assert (victim / "precious.txt").read_text() == "keep"
    assert not (victim / EXPANDED_MARKER).exists()
