from pathlib import Path, PureWindowsPath

import pytest

from behave_hive.privacy import scrub, user_home

CWD = Path("/Users/tester/project")
HOME = Path("/Users/tester")


@pytest.mark.parametrize(
    "text, expected",
    [
        (f'File "{CWD}/features/steps/login.py", line 7', 'File "features/steps/login.py", line 7'),
        (f'"{CWD}/support.py"', '"support.py"'),
        (f'"{HOME}/.venv/library.py"', '"~/.venv/library.py"'),
        (str(CWD), "."),
        (str(HOME), "~"),
        ("features/a.feature:7: assertion failed", "features/a.feature:7: assertion failed"),
        ("no path here", "no path here"),
        ("", ""),
        (f"{HOME}-other/a.py /other{HOME}/a.py", f"{HOME}-other/a.py /other{HOME}/a.py"),
        (f'"{CWD}/a path/file.py"', '"a path/file.py"'),
    ],
)
def test_scrub_rewrites_only_complete_path_prefixes(text, expected):
    assert scrub(text, CWD, HOME) == expected


def test_scrub_rewrites_multiple_paths_in_one_text():
    text = f"{CWD}/features/a.py\n{CWD}/b.py\n{HOME}/lib.py"
    assert scrub(text, CWD, HOME) == "features/a.py\nb.py\n~/lib.py"


def test_scrub_home_equal_to_cwd_prefers_project_relative_paths():
    assert scrub(f"{HOME}/a.py", HOME, HOME) == "a.py"


def test_user_home_is_none_when_the_home_directory_cannot_be_determined(monkeypatch):
    def unknown(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(unknown))
    assert user_home() is None


def test_user_home_is_the_home_directory(monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: HOME))
    assert user_home() == HOME


def test_scrub_without_a_home_directory_still_rewrites_project_paths():
    text = f'File "{CWD}/features/steps/login.py", line 7 in {CWD}/support.py'
    assert scrub(text, CWD, None) == 'File "features/steps/login.py", line 7 in support.py'


WIN_CWD = PureWindowsPath(r"C:\Users\ana\project")
WIN_HOME = PureWindowsPath(r"C:\Users\ana")


@pytest.mark.parametrize(
    "text, expected",
    [
        (r'File "C:\Users\ana\project\features\steps\login.py", line 7', 'File "features/steps/login.py", line 7'),
        (r"C:\\Users\\ana\\project\\features\\a.py", "features/a.py"),
        (r"c:\users\ANA\Project\x.py", "x.py"),
        ("C:/Users/ana/project/x.py", "x.py"),
        (r'"C:\Users\ana\AppData\Local\lib\site.py"', '"~/AppData/Local/lib/site.py"'),
        (r"C:\Users\ana\project", "."),
        (r"C:\Users\ana", "~"),
        (r"C:\Users\bob\x.py C:\Users\ana2\x.py", r"C:\Users\bob\x.py C:\Users\ana2\x.py"),
        ("features/a.feature:7: failed", "features/a.feature:7: failed"),
    ],
)
def test_scrub_rewrites_windows_paths_in_any_spelling(text, expected):
    assert scrub(text, WIN_CWD, WIN_HOME) == expected
    assert "ana" not in scrub(text, WIN_CWD, WIN_HOME).replace("ana2", "")


def test_scrub_windows_without_a_home_directory():
    assert scrub(r"C:\Users\ana\project\a.py C:\Users\ana\x.py", WIN_CWD, None) == r"a.py C:\Users\ana\x.py"
