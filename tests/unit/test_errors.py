from pathlib import Path

import pytest

from behave_hive.errors import ConfigError, ExamplesDataError, HiveError


def test_hive_error_exit_code_is_2():
    assert HiveError.exit_code == 2
    assert str(HiveError("boom")) == "boom"


def test_config_error_is_a_hive_error():
    assert issubclass(ConfigError, HiveError)
    assert ConfigError.exit_code == 2


def test_csv_examples_error_is_a_hive_error():
    assert issubclass(ExamplesDataError, HiveError)


def test_csv_examples_error_message_includes_all_locations():
    err = ExamplesDataError(
        "cell has a line break",
        feature=Path("features/login.feature"),
        line=7,
        data_path=Path("features/data/login.csv"),
        data_row=3,
    )
    msg = str(err)
    assert "features/login.feature" in msg
    assert "line 7" in msg
    assert "features/data/login.csv" in msg
    assert "row 3" in msg
    assert "cell has a line break" in msg
    assert (err.feature, err.line, err.data_path, err.data_row) == (
        Path("features/login.feature"),
        7,
        Path("features/data/login.csv"),
        3,
    )


def test_csv_examples_error_optional_locations_default_to_none():
    err = ExamplesDataError("bad", feature=Path("a.feature"), line=2)
    assert err.data_path is None
    assert err.data_row is None
    assert "row" not in str(err)
    assert "a.feature" in str(err) and "line 2" in str(err)


def test_csv_examples_error_without_any_location():
    err = ExamplesDataError("bad")
    assert err.feature is None and err.line is None
    assert str(err) == "bad"


def test_errors_can_be_raised_and_caught_as_hive_error():
    with pytest.raises(HiveError):
        raise ExamplesDataError("x")
