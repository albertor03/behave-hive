import os
import stat

import pytest

from behave_hive.errors import HiveError
from behave_hive.lock import LOCK_NAME, results_lock


def test_second_lock_on_the_same_directory_raises_and_deletes_nothing(tmp_path):
    results = tmp_path / "reports"
    results.mkdir()
    (results / "keep.txt").write_text("keep")
    with results_lock(results):
        with pytest.raises(HiveError, match="in use by another run"), results_lock(results):
            pytest.fail("the second lock must not be acquired")
        assert (results / "keep.txt").read_text() == "keep"
    assert (results / "keep.txt").read_text() == "keep"


def test_the_error_names_the_directory(tmp_path):
    with results_lock(tmp_path / "reports"), pytest.raises(HiveError) as exc, results_lock(tmp_path / "reports"):
        pass
    assert str(tmp_path / "reports") in str(exc.value)


def test_lock_is_released_on_exit(tmp_path):
    with results_lock(tmp_path / "reports"):
        pass
    with results_lock(tmp_path / "reports"):
        pass


def test_lock_is_released_when_the_body_raises(tmp_path):
    with pytest.raises(RuntimeError), results_lock(tmp_path / "reports"):
        raise RuntimeError("boom")
    with results_lock(tmp_path / "reports"):
        pass


def test_lock_creates_the_results_directory(tmp_path):
    with results_lock(tmp_path / "deep" / "reports"):
        assert (tmp_path / "deep" / "reports").is_dir()


def test_different_directories_do_not_conflict(tmp_path):
    with results_lock(tmp_path / "a"), results_lock(tmp_path / "b"):
        pass


@pytest.mark.parametrize("existing", [False, True])
def test_lock_permissions_are_owner_only_for_new_and_existing_files(tmp_path, existing):
    if existing:
        lock = tmp_path / LOCK_NAME
        lock.write_text("")
        lock.chmod(0o644)
    mask = os.umask(0)
    try:
        with results_lock(tmp_path):
            assert stat.S_IMODE((tmp_path / LOCK_NAME).stat().st_mode) == 0o600
    finally:
        os.umask(mask)
