import copy
from pathlib import Path

import pytest

from behave_hive.errors import HiveError
from behave_hive.expand import RowSource
from behave_hive.formatters.cucumber import feature_id
from behave_hive.merge import merge, pair_backgrounds, to_cucumber
from behave_hive.roots import PathMap

CWD = Path("/proj")
ORIGINAL = CWD / "features"
EXPANDED = CWD / ".behave-hive" / "run-1" / "roots" / "0" / "features"
PATH_MAP = PathMap({EXPANDED: ORIGINAL})
OLD_FID = "old-id"


def step(line=3, location=None):
    data = {"keyword": "Given ", "name": "x", "line": line, "result": {"status": "passed", "duration": 1}}
    if location:
        data["match"] = {"location": location}
    return data


def scenario(line, name="S", status="passed", fid=OLD_FID, location=None, tags=None):
    return {
        "id": f"{fid};{name.lower()}-l{line}",
        "keyword": "Scenario",
        "name": name,
        "description": "",
        "line": line,
        "type": "scenario",
        "tags": tags or [],
        "steps": [step(line + 1, location)],
        "x-behave-hive": {"status": status, "behave_status": status},
    }


def background(line=2, name="Shared"):
    return {
        "keyword": "Background", "name": name, "description": "", "line": line,
        "type": "background", "steps": [step(line + 1)],
    }


def feature(uri, elements, fid=OLD_FID, name="F"):
    return {
        "uri": uri, "id": fid, "keyword": "Feature", "name": name,
        "description": "", "line": 1, "tags": [], "elements": elements,
    }


def run(partials, sources=None):
    return merge(copy.deepcopy(partials), PATH_MAP, sources or {}, cwd=CWD)


def test_merge_rewrites_absolute_expanded_uri_to_the_original_relative_path():
    report = run([[feature(str(EXPANDED / "login.feature"), [scenario(3)])]])
    (feat,) = report.features
    assert feat["uri"] == "features/login.feature"


def test_merge_rewrites_relative_expanded_uri():
    relative = (EXPANDED / "auth" / "login.feature").relative_to(CWD).as_posix()
    report = run([[feature(relative, [scenario(3)])]])
    assert report.features[0]["uri"] == "features/auth/login.feature"


def test_merge_leaves_uris_outside_the_map_untouched():
    report = run([[feature("features/other.feature", [scenario(3)])]])
    assert report.features[0]["uri"] == "features/other.feature"


def test_merge_preserves_absolute_originals_outside_cwd():
    outside = Path("/shared/features")
    mapping = PathMap({EXPANDED: outside})
    report = merge(
        [[feature(str(EXPANDED / "a.feature"), [scenario(3, location=f"{EXPANDED}/steps/s.py:12")])]],
        mapping, {}, cwd=CWD,
    )
    (feat,) = report.features
    assert feat["uri"] == "/shared/features/a.feature"
    assert feat["elements"][0]["steps"][0]["match"]["location"] == "/shared/features/steps/s.py:12"


@pytest.mark.parametrize("hook_match", [None, {}, {"arguments": []}])
def test_merge_keeps_hooks_without_a_match_location(hook_match):
    hook = {"result": {"status": "failed", "duration": 0, "error_message": "setup failed"}}
    if hook_match is not None:
        hook["match"] = hook_match
    elem = scenario(3)
    elem["before"] = [hook]
    elem["after"] = [copy.deepcopy(hook)]
    report = run([[feature(str(EXPANDED / "a.feature"), [elem])]])
    out = report.features[0]["elements"][0]
    assert out["before"] == [hook] and out["after"] == [hook]


def test_merge_preserves_scenario_ids_without_the_old_feature_prefix():
    elem = scenario(3)
    elem["id"] = "external-scenario-id"
    report = run([[feature(str(EXPANDED / "a.feature"), [elem])]])
    (feat,) = report.features
    assert feat["id"] == feature_id("features/a.feature")
    assert feat["elements"][0]["id"] == "external-scenario-id"


def test_merge_recomputes_feature_and_scenario_ids_over_the_original_uri():
    report = run([[feature(str(EXPANDED / "login.feature"), [scenario(3, "Login")])]])
    (feat,) = report.features
    expected = feature_id("features/login.feature")
    assert feat["id"] == expected
    assert feat["elements"][0]["id"] == f"{expected};login-l3"


def test_merge_rewrites_match_locations_keeping_the_line_and_leaves_hooks_alone():
    location = f"{EXPANDED}/steps/s.py:12"
    elem = scenario(3, location=location)
    elem["before"] = [{"match": {"location": "environment.py"}, "result": {"status": "failed", "duration": 0}}]
    report = run([[feature(str(EXPANDED / "a.feature"), [elem])]])
    out = report.features[0]["elements"][0]
    assert out["steps"][0]["match"]["location"] == "features/steps/s.py:12"
    assert out["before"][0]["match"]["location"] == "environment.py"


def test_merge_joins_features_with_the_same_uri_and_sorts_scenarios_by_line():
    uri = str(EXPANDED / "login.feature")
    partials = [
        [feature(uri, [scenario(9, "C"), scenario(5, "B")])],
        [feature(uri, [scenario(3, "A")])],
    ]
    (feat,) = run(partials).features
    assert [e["line"] for e in feat["elements"]] == [3, 5, 9]


def test_merge_keeps_each_background_right_before_its_scenario():
    uri = str(EXPANDED / "login.feature")
    partials = [
        [feature(uri, [background(), scenario(9, "C"), background(), scenario(5, "B")])],
        [feature(uri, [background(), scenario(3, "A")])],
    ]
    (feat,) = run(partials).features
    assert [(e["type"], e["line"]) for e in feat["elements"]] == [
        ("background", 2), ("scenario", 3),
        ("background", 2), ("scenario", 5),
        ("background", 2), ("scenario", 9),
    ]


def test_merge_scenarios_without_background_stay_unpaired():
    uri = str(EXPANDED / "login.feature")
    (feat,) = run([[feature(uri, [scenario(5), background(), scenario(3)])]]).features
    assert [(e["type"], e["line"]) for e in feat["elements"]] == [("background", 2), ("scenario", 3), ("scenario", 5)]


def test_merge_sorts_features_by_uri():
    partials = [
        [feature("features/b.feature", [scenario(3)], name="B")],
        [feature("features/a.feature", [scenario(3)], name="A")],
    ]
    assert [f["uri"] for f in run(partials).features] == ["features/a.feature", "features/b.feature"]


def test_merge_keeps_the_metadata_of_the_first_partial():
    uri = str(EXPANDED / "login.feature")
    partials = [[feature(uri, [scenario(3)], name="First")], [feature(uri, [scenario(5)], name="Second")]]
    assert run(partials).features[0]["name"] == "First"


def test_merge_attaches_the_row_source():
    uri = EXPANDED / "login.feature"
    sources = {uri: [
        RowSource(3, CWD / "features" / "data" / "login.csv", 2),
        RowSource(5, CWD / "features" / "data" / "login.csv", 3),
    ]}
    (feat,) = run([[feature(str(uri), [scenario(3), scenario(5), scenario(7)])]], sources).features
    assert [e["x-behave-hive"].get("source") for e in feat["elements"]] == [
        {"data_path": "features/data/login.csv", "data_row": 2},
        {"data_path": "features/data/login.csv", "data_row": 3},
        None,
    ]


def test_merge_duplicate_scenario_ids_are_a_bug():
    uri = str(EXPANDED / "login.feature")
    with pytest.raises(HiveError, match="duplicate"):
        run([[feature(uri, [scenario(3)])], [feature(uri, [scenario(3)])]])


def test_to_cucumber_removes_the_internal_extension_without_touching_the_report():
    report = run([[feature(str(EXPANDED / "a.feature"), [background(), scenario(3)])]])
    cucumber = to_cucumber(report)
    assert all("x-behave-hive" not in e for e in cucumber[0]["elements"])
    assert "x-behave-hive" in report.features[0]["elements"][1]


def test_scrub_error_messages_in_steps_and_both_hooks(monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/tester")))
    message = f'File "{EXPANDED}/steps/s.py"\nFile "/Users/tester/library.py"'
    elem = scenario(3, status="failed")
    elem["steps"][0]["result"].update(status="failed", error_message=message)
    hook = {"result": {"status": "failed", "duration": 0, "error_message": message}}
    elem["before"], elem["after"] = [hook], [copy.deepcopy(hook)]
    (out,) = run([[feature(str(EXPANDED / "a.feature"), [elem])]]).features[0]["elements"]
    expected = 'File "features/steps/s.py"\nFile "~/library.py"'
    assert out["steps"][0]["result"]["error_message"] == expected
    assert out["before"][0]["result"]["error_message"] == expected
    assert out["after"][0]["result"]["error_message"] == expected


def test_pair_backgrounds_pairs_a_background_only_with_the_next_scenario():
    background = {"type": "background", "name": "bg"}
    first, second, third = ({"type": "scenario", "name": n} for n in "abc")
    assert pair_backgrounds([background, first, second, third]) == [(background, first), (None, second), (None, third)]


def test_pair_backgrounds_of_nothing_is_empty():
    assert pair_backgrounds([]) == []
