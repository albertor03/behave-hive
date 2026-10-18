from pathlib import Path

import pytest

from behave_hive.errors import CsvExamplesError
from behave_hive.expand import read_csv_rows


def write(tmp_path: Path, content: bytes, name: str = "d.csv") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def err(path: Path) -> CsvExamplesError:
    with pytest.raises(CsvExamplesError) as exc:
        read_csv_rows(path, feature=Path("f.feature"), line=9)
    return exc.value


def test_csv_reads_header_and_rows(tmp_path):
    path = write(tmp_path, b"user,password\nadmin,secret\n")
    assert read_csv_rows(path) == [["user", "password"], ["admin", "secret"]]


def test_csv_bom_is_stripped_from_first_header(tmp_path):
    path = write(tmp_path, b"\xef\xbb\xbfuser,password\na,b\n")
    assert read_csv_rows(path)[0][0] == "user"


def test_csv_ignores_physically_empty_lines_and_keeps_empty_cells(tmp_path):
    path = write(tmp_path, b"user,password\n\nadmin,\n\n")
    assert read_csv_rows(path) == [["user", "password"], ["admin", ""]]


def test_csv_quoted_comma_and_pipe_are_kept(tmp_path):
    path = write(tmp_path, b'v\n"a,b"\na|b\n')
    assert read_csv_rows(path) == [["v"], ["a,b"], ["a|b"]]


def test_csv_missing_file(tmp_path):
    e = err(tmp_path / "missing.csv")
    assert e.csv_path == tmp_path / "missing.csv"
    assert (e.feature, e.line) == (Path("f.feature"), 9)
    assert "missing.csv" in str(e) and "f.feature" in str(e) and "line 9" in str(e)


@pytest.mark.parametrize("content", [b"", b"user,password\n", b"\n\n"])
def test_csv_without_data_rows(tmp_path, content):
    e = err(write(tmp_path, content))
    assert "data row" in str(e)


@pytest.mark.parametrize(
    "content",
    [b"a,,c\n1,2,3\n", b"a, ,c\n1,2,3\n", b",b\n1,2\n"],
)
def test_csv_empty_header(tmp_path, content):
    e = err(write(tmp_path, content))
    assert e.csv_row == 1
    assert "empty header" in str(e)


@pytest.mark.parametrize("content", [b"v,v\n1,2\n", b"v, v\n1,2\n", b"v,v \n1,2\n"])
def test_csv_duplicated_header_after_strip(tmp_path, content):
    e = err(write(tmp_path, content))
    assert e.csv_row == 1
    assert "duplicated header" in str(e)


def test_csv_row_with_different_width_reports_row_number(tmp_path):
    e = err(write(tmp_path, b"a,b,c\n1,2,3\n4,5\n"))
    assert e.csv_row == 3
    assert "row 3" in str(e)


@pytest.mark.parametrize("cell", [b"x\ny", b"x\ry"])
def test_csv_cell_with_line_break_reports_row_number(tmp_path, cell):
    e = err(write(tmp_path, b'v\nok\n"' + cell + b'"\n'))
    assert e.csv_row == 3
    assert "line break" in str(e)


def test_csv_invalid_utf8(tmp_path):
    e = err(write(tmp_path, b"v\n\xff\xfe\n"))
    assert "UTF-8" in str(e)


def test_csv_directory_is_unreadable(tmp_path):
    e = err(tmp_path)
    assert e.csv_path == tmp_path
