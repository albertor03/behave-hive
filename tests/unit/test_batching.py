from pathlib import Path

from behave_hive.batching import Batch, effective_workers, make_batches
from behave_hive.discovery import Unit

ROOT_A, ROOT_B = Path("/a/features"), Path("/b/features")


def units(root: Path, n: int) -> list[Unit]:
    return [Unit(root / "x.feature", line) for line in range(1, n + 1)]


def sizes(batches: list[Batch]) -> list[int]:
    return [len(b.units) for b in batches]


def test_effective_workers():
    assert effective_workers(4, parallel=True) == 4
    assert effective_workers(4, parallel=False) == 1


def test_automatic_chunk_splits_ten_units_for_four_workers_into_3_3_3_1():
    batches = make_batches({ROOT_A: units(ROOT_A, 10)}, workers=4, chunk=0, parallel=True)
    assert sizes(batches) == [3, 3, 3, 1]
    assert [u for b in batches for u in b.units] == units(ROOT_A, 10)


def test_batches_are_numbered_from_one():
    batches = make_batches({ROOT_A: units(ROOT_A, 10)}, workers=4, chunk=0, parallel=True)
    assert [b.index for b in batches] == [1, 2, 3, 4]


def test_explicit_chunk_of_one():
    batches = make_batches({ROOT_A: units(ROOT_A, 4)}, workers=2, chunk=1, parallel=True)
    assert sizes(batches) == [1, 1, 1, 1]


def test_explicit_chunk_larger_than_the_total_gives_one_batch():
    batches = make_batches({ROOT_A: units(ROOT_A, 4)}, workers=2, chunk=100, parallel=True)
    assert sizes(batches) == [4]


def test_explicit_chunk_leaves_a_shorter_last_batch():
    batches = make_batches({ROOT_A: units(ROOT_A, 5)}, workers=2, chunk=2, parallel=True)
    assert sizes(batches) == [2, 2, 1]


def test_empty_list_gives_no_batches():
    assert make_batches({}, workers=4, chunk=0, parallel=True) == []
    assert make_batches({ROOT_A: []}, workers=4, chunk=0, parallel=True) == []


def test_sequential_mode_is_one_batch_per_root_even_with_many_workers():
    batches = make_batches({ROOT_A: units(ROOT_A, 10), ROOT_B: units(ROOT_B, 3)}, workers=4, chunk=2, parallel=False)
    assert sizes(batches) == [10, 3]
    assert [b.root for b in batches] == [ROOT_A, ROOT_B]


def test_two_roots_never_share_a_batch_and_keep_input_order():
    batches = make_batches({ROOT_A: units(ROOT_A, 5), ROOT_B: units(ROOT_B, 5)}, workers=2, chunk=0, parallel=True)
    assert sizes(batches) == [3, 2, 3, 2]
    assert [b.root for b in batches] == [ROOT_A, ROOT_A, ROOT_B, ROOT_B]
    assert [b.index for b in batches] == [1, 2, 3, 4]
    for batch in batches:
        assert all(u.path.is_relative_to(batch.root) for u in batch.units)
