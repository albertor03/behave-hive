from pathlib import Path

import pytest

from behave_hive.privacy import scrub
from behave_hive.roots import PathMap

CWD = Path("/Users/tester/project")
HOME = Path("/Users/tester")
EXPANDED = CWD / ".behave-hive/run-123/roots/0/features"
MAPPING = PathMap({EXPANDED: CWD / "features"})


@pytest.mark.parametrize(
    "text, expected",
    [
        (f'File "{EXPANDED}/steps/login.py", line 7', 'File "features/steps/login.py", line 7'),
        ('.behave-hive/run-123/roots/0/features/steps/login.py:7', 'features/steps/login.py:7'),
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
    assert scrub(text, MAPPING, CWD, HOME) == expected


def test_scrub_prefers_longest_overlapping_mapping_and_rewrites_multiple_paths():
    mapping = PathMap({EXPANDED: CWD / "features", EXPANDED / "nested": CWD / "other"})
    text = f"{EXPANDED}/nested/a.py\n{EXPANDED}/b.py\n{HOME}/lib.py"
    assert scrub(text, mapping, CWD, HOME) == "other/a.py\nfeatures/b.py\n~/lib.py"


def test_scrub_original_outside_cwd_keeps_path_but_rewrites_home():
    mapping = PathMap({EXPANDED: HOME / "shared", EXPANDED / "external": Path("/shared")})
    assert scrub(f"{EXPANDED}/a.py", mapping, CWD, HOME) == "~/shared/a.py"
    assert scrub(f"{EXPANDED}/external/a.py", mapping, CWD, HOME) == "/shared/a.py"


def test_scrub_mapping_outside_cwd_and_project_root_preserves_relative_paths():
    mapping = PathMap({Path("/elsewhere/expanded"): CWD})
    assert scrub("/elsewhere/expanded/a.py /elsewhere/expanded", mapping, CWD, HOME) == "a.py ."
    assert dict(mapping.items()) == {"/elsewhere/expanded": str(CWD)}


def test_scrub_home_equal_to_cwd_prefers_project_relative_paths():
    assert scrub(f"{HOME}/a.py", PathMap({}), HOME, HOME) == "a.py"
