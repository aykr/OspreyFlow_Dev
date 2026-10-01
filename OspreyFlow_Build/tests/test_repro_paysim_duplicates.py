"""The reproduction of the eight duplicated PaySim transactions — ADR-056 Amendment 9.

The script replays the real seed's graph load into a throwaway database and reports each duplicated
id with the batch that wrote it, and which batches had a commit replayed by the client. What is
tested here is the part that can be wrong without anyone noticing: a replay attributed to the wrong
batch would send the investigation the wrong way; a refused data gate that still touched a database
would be worse.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from scripts import repro_paysim_duplicates as repro

_CLIENT = "adapters.graph_arcadedb.client"


def _replay_warning() -> None:
    logging.getLogger(_CLIENT).warning(
        "arcadedb: commit of session s1 failed (500: X); replaying its 40 recorded commands in a "
        "new transaction (attempt 1 of 3)"
    )


def test_a_replay_is_attributed_to_the_batch_that_was_running_when_it_happened() -> None:
    """Catches an off-by-one that blames the next batch, and a replay that is never attributed."""
    clock = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    watcher = repro.ReplayWatcher(clock=lambda: next(clock))
    logger = logging.getLogger(_CLIENT)
    logger.addHandler(watcher)
    try:
        watcher.batch_done("transactions", 0)
        _replay_warning()  # happens during batch 1 ...
        watcher.batch_done("transactions", 1)  # ... and is reported when batch 1 finishes
        watcher.batch_done("transactions", 2)
    finally:
        logger.removeHandler(watcher)

    assert [(noun, index) for noun, index, _ in watcher.replayed] == [("transactions", 1)]


def test_a_slow_batch_is_listed_with_how_long_it_took() -> None:
    """A commit that took long enough to time out is the other thing worth lining up."""
    clock = iter([0.0, 1.0, 13.0])
    watcher = repro.ReplayWatcher(clock=lambda: next(clock), slow_seconds=10.0)

    watcher.batch_done("transactions", 0)
    watcher.batch_done("transactions", 1)

    assert watcher.slow == [("transactions", 1, 12.0)]


def test_other_warnings_are_not_counted_as_replays() -> None:
    watcher = repro.ReplayWatcher(clock=lambda: 0.0)
    logger = logging.getLogger(_CLIENT)
    logger.addHandler(watcher)
    try:
        logger.warning("something else entirely")
        watcher.batch_done("transactions", 0)
    finally:
        logger.removeHandler(watcher)

    assert watcher.replayed == []


def test_a_duplicated_id_is_mapped_to_the_batch_that_wrote_it() -> None:
    edge_ids = [f"tx-{i}" for i in range(100)]
    assert repro.duplicate_batches(edge_ids, ["tx-0", "tx-39", "tx-40", "tx-99"], chunk=40) == {
        "tx-0": 0,
        "tx-39": 0,
        "tx-40": 1,
        "tx-99": 2,
    }


def test_an_id_the_load_never_wrote_is_reported_not_dropped() -> None:
    """Catches a duplicate that could not be placed being silently left out of the report."""
    assert repro.duplicate_batches(["a"], ["a", "zzz"], chunk=40) == {"a": 0, "zzz": -1}


def test_a_missing_dataset_is_refused_before_any_database_is_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real-data gate is the seed's own; a refusal must not create a database first."""

    def _must_not_be_called(*_: object, **__: object) -> None:
        raise AssertionError("a database was opened although the dataset was refused")

    monkeypatch.setattr(repro, "arcadedb_adapter", _must_not_be_called)

    assert repro.main(["--data-dir", str(tmp_path)]) == 1
    assert "dataset not provisioned" in capsys.readouterr().err


def test_a_batch_is_checked_against_exactly_the_ids_it_wrote() -> None:
    """Catches a check that passes when an id is missing or stored twice, and one that blames an
    id from another batch."""
    wrote = ["a", "b", "c"]
    assert repro.batch_faults(wrote, {"a": 1, "b": 1, "c": 1}) == {}
    assert repro.batch_faults(wrote, {"a": 1, "b": 2, "c": 1}) == {"b": 2}
    assert repro.batch_faults(wrote, {"a": 1, "c": 1}) == {"b": 0}
    assert repro.batch_faults(wrote, {"a": 1, "b": 1, "c": 1, "z": 2}) == {}


def test_a_limited_run_keeps_the_first_batches_and_only_the_accounts_they_touch() -> None:
    """Catches a limit that cuts a batch short, and one that leaves out an endpoint an edge needs
    (the adapter refuses an edge whose endpoint does not exist)."""

    class N:
        def __init__(self, id: str) -> None:
            self.id = id

    class E:
        def __init__(self, id: str, source: str, target: str) -> None:
            self.id, self.source, self.target = id, source, target

    nodes = [N(x) for x in "abcdef"]
    edges = [E("1", "a", "b"), E("2", "b", "c"), E("3", "d", "e"), E("4", "e", "f")]
    kept_nodes, kept_edges = repro.limit_batches(nodes, edges, batches=1, chunk=2)  # type: ignore[arg-type]
    assert [e.id for e in kept_edges] == ["1", "2"]
    assert [n.id for n in kept_nodes] == ["a", "b", "c"]
    assert repro.limit_batches(nodes, edges, batches=None, chunk=2) == (nodes, edges)  # type: ignore[arg-type]


def test_a_duplicated_id_is_matched_to_other_edges_between_the_same_two_accounts() -> None:
    """Seen 1 October 2026: duplicates were not there right after their own batch committed, so a
    later write is the suspect, and a later write to the same pair takes the adapter's merge path.
    Catches a match on one end only, one that ignores direction (the type is directed), and one
    that lists the edge as its own twin."""

    class E:
        def __init__(self, id: str, source: str, target: str) -> None:
            self.id, self.source, self.target = id, source, target

    edges = [E("1", "a", "b"), E("2", "b", "a"), E("3", "a", "b"), E("4", "a", "c")]
    found = repro.same_pair_edges(edges, ["1", "4"], chunk=2)  # type: ignore[arg-type]
    assert found == {"1": [("3", 1)], "4": []}


def test_the_first_batch_after_which_each_duplicate_is_seen_is_remembered_once() -> None:
    """Catches a duplicate re-reported after every later batch, and one reported against the batch
    that wrote it when it only showed up later."""
    seen: dict[str, int] = {}
    assert repro.note_new_faults(seen, {"x": 2}, index=3) == ["x"]
    assert repro.note_new_faults(seen, {"x": 2, "y": 0}, index=4) == ["y"]
    assert seen == {"x": 3, "y": 4}
