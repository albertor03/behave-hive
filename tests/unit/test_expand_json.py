import json
from pathlib import Path

import pytest

from behave_hive.errors import ExamplesDataError
from behave_hive.expand import read_json_rows


def write(tmp_path: Path, content: bytes | str | object, name: str = "d.json") -> Path:
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    elif isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return path


def err(path: Path) -> ExamplesDataError:
    with pytest.raises(ExamplesDataError) as exc:
        read_json_rows(path, feature=Path("f.feature"), line=9)
    return exc.value


def test_json_reads_header_and_rows(tmp_path):
    path = write(tmp_path, [{"user": "a", "password": "1"}, {"user": "b", "password": "2"}])
    assert read_json_rows(path) == [["user", "password"], ["a", "1"], ["b", "2"]]


def test_json_bom_is_accepted(tmp_path):
    path = write(tmp_path, b'\xef\xbb\xbf[{"v": "a"}]')
    assert read_json_rows(path) == [["v"], ["a"]]


def test_json_values_follow_the_header_order_of_the_first_object(tmp_path):
    path = write(tmp_path, [{"a": "1", "b": "2"}, {"b": "4", "a": "3"}])
    assert read_json_rows(path) == [["a", "b"], ["1", "2"], ["3", "4"]]


def test_json_scalars_are_rendered_as_json_writes_them(tmp_path):
    path = write(tmp_path, [{"s": "a|b", "i": 30, "f": 1.5, "t": True, "n": False, "z": None}])
    assert read_json_rows(path)[1] == ["a|b", "30", "1.5", "true", "false", ""]


def test_json_keys_are_stripped(tmp_path):
    path = write(tmp_path, [{" a ": "1", "b": "2"}, {"a": "3", " b": "4"}])
    assert read_json_rows(path) == [["a", "b"], ["1", "2"], ["3", "4"]]


def test_json_missing_file(tmp_path):
    e = err(tmp_path / "missing.json")
    assert e.data_path == tmp_path / "missing.json"
    assert "missing.json" in str(e) and "f.feature" in str(e) and "line 9" in str(e)


def test_json_directory_is_unreadable(tmp_path):
    assert err(tmp_path).data_path == tmp_path


def test_json_invalid_utf8(tmp_path):
    assert "UTF-8" in str(err(write(tmp_path, b'[{"v": "\xff"}]')))


def test_json_syntax_error_names_line_and_column(tmp_path):
    e = err(write(tmp_path, '[\n{"v": "a"},\n{"v": }\n]'))
    assert "line 3" in str(e) and "column 7" in str(e)
    assert e.data_row is None


@pytest.mark.parametrize("content", [{"v": "a"}, "\"text\"", 3, None])
def test_json_top_level_must_be_an_array(tmp_path, content):
    assert "array of objects" in str(err(write(tmp_path, content)))


def test_json_empty_array(tmp_path):
    assert "at least one object" in str(err(write(tmp_path, [])))


def test_json_element_must_be_an_object(tmp_path):
    e = err(write(tmp_path, [{"v": "a"}, "b"]))
    assert e.data_row == 2
    assert "object" in str(e)


def test_json_empty_key(tmp_path):
    e = err(write(tmp_path, [{" ": "a"}]))
    assert e.data_row == 1
    assert "empty key" in str(e)


def test_json_duplicated_key_after_stripping(tmp_path):
    e = err(write(tmp_path, [{"v": "a", " v": "b"}]))
    assert e.data_row == 1
    assert "duplicated key" in str(e)


def test_json_key_repeated_inside_an_object(tmp_path):
    e = err(write(tmp_path, '[{"v": "a", "v": "b"}]'))
    assert "duplicated key" in str(e)


def test_json_missing_key_names_element_and_key(tmp_path):
    e = err(write(tmp_path, [{"user": "a", "password": "1"}, {"user": "b"}]))
    assert e.data_row == 2
    assert "missing" in str(e) and "password" in str(e)


def test_json_extra_key_names_element_and_key(tmp_path):
    e = err(write(tmp_path, [{"user": "a"}, {"user": "b", "role": "x"}]))
    assert e.data_row == 2
    assert "unexpected" in str(e) and "role" in str(e)


@pytest.mark.parametrize("value", ["a\nb", "a\rb"])
def test_json_string_with_line_break(tmp_path, value):
    e = err(write(tmp_path, [{"v": "ok"}, {"v": value}]))
    assert e.data_row == 2
    assert "line break" in str(e)


@pytest.mark.parametrize("value", [{"city": "Lima"}, [1, 2]])
def test_json_nested_value(tmp_path, value):
    e = err(write(tmp_path, [{"a": "1", "v": value}]))
    assert e.data_row == 1
    assert "'v'" in str(e) and "nested" in str(e)


def test_json_key_with_a_line_break(tmp_path):
    e = err(write(tmp_path, [{"a\nb": "1"}]))
    assert e.data_row == 1
