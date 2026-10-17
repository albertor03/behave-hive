import pytest

from behave_hive import cli


def test_version_prints_name_and_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "behave-hive 0.1.0"


def test_split_argv_at_the_first_double_dash():
    assert cli.split_argv(["run", "-x", "--", "-t", "@a", "--", "b"]) == (["run", "-x"], ["-t", "@a", "--", "b"])
    assert cli.split_argv(["run"]) == (["run"], [])


def make_features(tmp_path, csv=True):
    root = tmp_path / "features"
    (root / "steps").mkdir(parents=True)
    ref = "read('v.csv')" if csv else "x"
    (root / "a.feature").write_text(
        f"Feature: F\n  Scenario Outline: S\n    Given x\n    Examples:\n      | {ref} |\n"
    )
    (root / "v.csv").write_text("v\n1\n")
    return root


def test_expand_writes_the_expanded_tree(tmp_path, capsys):
    src = make_features(tmp_path)
    dst = tmp_path / "out"
    assert cli.main(["expand", str(src), str(dst)]) == 0
    assert "| v |\n      | 1 |" in (dst / "a.feature").read_text()
    assert (dst / "v.csv").is_symlink()


def test_expand_reexpansion_removes_stale_feature(tmp_path):
    src = make_features(tmp_path)
    dst = tmp_path / "out"
    assert cli.main(["expand", str(src), str(dst)]) == 0
    (dst / "gone.feature").write_text("Feature: stale\n")
    assert cli.main(["expand", str(src), str(dst)]) == 0
    assert not (dst / "gone.feature").exists()


def test_expand_dangerous_destination_exits_2_without_deleting(tmp_path, monkeypatch, capsys):
    src = make_features(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["expand", "features", "."]) == 2
    assert capsys.readouterr().err.startswith("behave-hive: error: ")
    assert (src / "a.feature").is_file() and (src / "v.csv").is_file()


def test_expand_csv_error_exits_2_with_message_and_no_traceback(tmp_path, capsys):
    src = make_features(tmp_path)
    (src / "v.csv").unlink()
    assert cli.main(["expand", str(src), str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("behave-hive: error: ")
    assert "v.csv" in err and "Traceback" not in err
