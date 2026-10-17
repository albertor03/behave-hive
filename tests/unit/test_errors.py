from pathlib import Path

import pytest

from behave_hive.errors import ConfigError, CsvExamplesError, HiveError


def test_hive_error_exit_code_is_2():
    assert HiveError.exit_code == 2
    assert str(HiveError("boom")) == "boom"


def test_config_error_is_a_hive_error():
    assert issubclass(ConfigError, HiveError)
    assert ConfigError.exit_code == 2


def test_csv_examples_error_is_a_hive_error():
    assert issubclass(CsvExamplesError, HiveError)


def test_csv_examples_error_message_includes_all_locations():
    err = CsvExamplesError(
        "cell has a line break",
        feature=Path("features/login.feature"),
        line=7,
        csv_path=Path("features/data/login.csv"),
        csv_row=3,
    )
    msg = str(err)
    assert "features/login.feature" in msg
    assert "line 7" in msg
    assert "features/data/login.csv" in msg
    assert "row 3" in msg
    assert "cell has a line break" in msg
    assert (err.feature, err.line, err.csv_path, err.csv_row) == (
        Path("features/login.feature"),
        7,
        Path("features/data/login.csv"),
        3,
    )


def test_csv_examples_error_optional_locations_default_to_none():
    err = CsvExamplesError("bad", feature=Path("a.feature"), line=2)
    assert err.csv_path is None
    assert err.csv_row is None
    assert "row" not in str(err)
    assert "a.feature" in str(err) and "line 2" in str(err)


def test_csv_examples_error_without_any_location():
    err = CsvExamplesError("bad")
    assert err.feature is None and err.line is None
    assert str(err) == "bad"


def test_errors_can_be_raised_and_caught_as_hive_error():
    with pytest.raises(HiveError):
        raise CsvExamplesError("x")
