"""Stray edge records, and putting them right (ADR-056 Amendments 9 to 17).

Seen, 1 October 2026: ArcadeDB stored a few edges twice during a load (13,076 records for 13,068
written). A traversal reaches each such edge once; the second record is a stray that only a scan
sees. It inflates every scan-based count, including the adapter's corpus total behind edge weights.

The first repair deleted the stray by its record id and kept the other. Run against the real store
on one id, the delete took BOTH records: the id was left with none, and one transaction was lost.
So the repair no longer trusts a delete to touch one record. For a stray it removes every copy,
checks none is left, writes the edge once more through the normal write path, and checks that
exactly one record is stored and the source reaches it once. A missing edge is written the same
way. Each id is checked before the next is touched, and the first surprise stops the run (rule 15:
the fake below models what the real store did, not what we hoped it would do).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from scripts import seed_support as ss

TYPE = "TRANSACTED"
PREFIX = "paysim-tx-"


class Store:
    """Edge records by id: every stored copy, and which records each source's edge list reaches."""

    def __init__(self) -> None:
        self.copies: dict[str, list[dict[str, str]]] = {}
        self.reachable: dict[str, list[str]] = {}
        self.deleted: list[str] = []
        self.written: list[str] = []
        self.statements: list[str] = []
        self._next = 100
        #: What the real ArcadeDB did (1 October 2026): deleting a stray by its record id removed
        #: every record that shared the id, the real edge included.
        self.delete_takes_every_copy = True
        #: A delete that quietly does nothing.
        self.delete_does_nothing = False
        #: A write that itself leaves a stray (the original defect, hitting the rewrite).
        self.write_leaves_a_stray = False
        #: A write the source's edge list does not reach.
        self.write_is_not_linked = False

    def add(self, edge_id: str, rids: list[str], reached: list[str], source: str = "a") -> None:
        self.copies[edge_id] = [{"rid": r, "id": edge_id, "source": source} for r in rids]
        self.reachable[edge_id] = list(reached)

    def write(self, edge_id: str, source: str = "a") -> None:
        """What `rewrite` does: one new record, linked to the source."""
        self.written.append(edge_id)
        self._next += 1
        rid = f"#9:{self._next}"
        records = self.copies.setdefault(edge_id, [])
        records.append({"rid": rid, "id": edge_id, "source": source})
        self.reachable[edge_id] = [] if self.write_is_not_linked else [rid]
        if self.write_leaves_a_stray:
            records.append({"rid": f"#9:{self._next + 500}", "id": edge_id, "source": source})

    async def sql(self, command: str, *, params: Any = None, session_id: Any = None) -> list[Any]:
        self.statements.append(command)
        if "GROUP BY id" in command:
            return [{"id": i, "n": len(c)} for i, c in self.copies.items() if c]
        if command.startswith("SELECT @rid AS rid"):
            wanted = re.search(r"LIKE '([^']*)'", command)
            assert wanted
            return list(self.copies.get(wanted.group(1), []))
        if command.startswith("SELECT id FROM"):
            like = re.search(r"LIKE '([^']*)%'", command)
            skip = re.search(r"SKIP (\d+)", command)
            limit = re.search(r"LIMIT (\d+)", command)
            assert like and skip and limit, command
            ids = sorted(
                i for i, c in self.copies.items() for _ in c if i.startswith(like.group(1))
            )
            window = ids[int(skip.group(1)) : int(skip.group(1)) + int(limit.group(1))]
            return [{"id": i} for i in window]
        if command.startswith("DELETE FROM"):
            rid = re.search(r"@rid = (#\d+:\d+)", command)
            assert rid, command
            self.deleted.append(rid.group(1))
            if self.delete_does_nothing:
                return [{"count": 0}]
            for edge_id, copies in self.copies.items():
                if any(c["rid"] == rid.group(1) for c in copies):
                    gone = (
                        copies
                        if self.delete_takes_every_copy
                        else [c for c in copies if c["rid"] == rid.group(1)]
                    )
                    self.copies[edge_id] = [c for c in copies if c not in gone]
                    self.reachable[edge_id] = [
                        r for r in self.reachable[edge_id] if r not in [g["rid"] for g in gone]
                    ]
            return [{"count": 1}]
        raise AssertionError(f"unexpected statement: {command}")

    async def gremlin(
        self, command: str, *, params: Any = None, session_id: Any = None
    ) -> list[Any]:
        self.statements.append(command)
        found = [i for i in self.copies if i in command]
        assert len(found) == 1, command
        reached = self.reachable[found[0]]
        if command.endswith(".count()"):
            return [{"result": len(reached)}]
        assert command.endswith(".id()")
        return [{"result": r} for r in reached]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _expected(*ids: str, source: str = "a") -> dict[str, str]:
    return {i: source for i in ids}


def _rewriter(store: Store) -> Any:
    async def rewrite(edge_id: str) -> None:
        store.write(edge_id)

    return rewrite


def _repair(store: Store, expected: dict[str, str], **kw: Any) -> ss.RepairReport:
    lines: list[str] = []
    kw.setdefault("apply", False)
    report: ss.RepairReport = _run(
        ss.repair_ids_stored_twice(
            store,
            edge_type=TYPE,
            prefix=PREFIX,
            expected=expected,
            rewrite=_rewriter(store),
            say=lines.append,
            **kw,
        )
    )
    report.lines = lines  # type: ignore[attr-defined]
    return report


def _restore(store: Store, expected: dict[str, str], **kw: Any) -> ss.RepairReport:
    lines: list[str] = []
    kw.setdefault("apply", False)
    report: ss.RepairReport = _run(
        ss.restore_missing_edges(
            store,
            edge_type=TYPE,
            prefix=PREFIX,
            expected=expected,
            rewrite=_rewriter(store),
            say=lines.append,
            **kw,
        )
    )
    report.lines = lines  # type: ignore[attr-defined]
    return report


def test_only_ids_stored_more_than_once_under_the_prefix_are_found() -> None:
    """Catches a check that reports every id, one that ignores the prefix (another seed's rows),
    and one that misses the repeated id."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    store.add("other-3", ["#1:3", "#1:8"], ["#1:3"])
    assert _run(ss.ids_stored_twice(store, edge_type=TYPE, prefix=PREFIX)) == ["paysim-tx-2"]


def test_a_dry_run_changes_nothing_and_says_what_it_would_do() -> None:
    """Catches a repair that deletes or writes without being told to, or reports nothing."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    report = _repair(store, _expected("paysim-tx-2"))
    assert store.deleted == [] and store.written == []
    assert report.planned == [("paysim-tx-2", ["#1:2", "#1:9"])]
    text = "\n".join(report.lines)  # type: ignore[attr-defined]
    assert "would" in text and "#1:2" in text and "#1:9" in text


def test_every_copy_is_removed_and_the_edge_is_written_once() -> None:
    """The observed case: the first delete takes both records. Catches a repair that assumes it
    kept one (it would then write a second edge, or none), and one that never writes the edge
    back, which is how a transaction was lost."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    report = _repair(store, _expected("paysim-tx-2"), apply=True)
    assert store.written == ["paysim-tx-2"] and report.written == ["paysim-tx-2"]
    assert [c["id"] for c in store.copies["paysim-tx-2"]] == ["paysim-tx-2"]
    assert len(store.reachable["paysim-tx-2"]) == 1


def test_a_delete_that_takes_only_one_record_is_still_handled() -> None:
    """The fake must not hard-code the surprise: if a delete removes one record, the next is
    removed too. Catches a repair that only works for the behaviour first seen."""
    store = Store()
    store.delete_takes_every_copy = False
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    _repair(store, _expected("paysim-tx-2"), apply=True)
    assert sorted(store.deleted) == ["#1:2", "#1:9"]
    assert len(store.copies["paysim-tx-2"]) == 1


def test_a_record_already_gone_is_not_deleted_again() -> None:
    """Catches a second DELETE for a record the first one already took."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    _repair(store, _expected("paysim-tx-2"), apply=True)
    assert len(store.deleted) == 1


def test_the_delete_names_the_record_and_the_type_not_the_id() -> None:
    """Catches `DELETE ... WHERE id = ...`, which an index can answer for only one record."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    _repair(store, _expected("paysim-tx-2"), apply=True)
    deletes = [s for s in store.statements if s.startswith("DELETE")]
    assert deletes and all(
        re.fullmatch(rf"DELETE FROM {TYPE} WHERE @rid = #\d+:\d+", d) for d in deletes
    )


def test_nothing_is_written_over_records_that_a_delete_failed_to_remove() -> None:
    """Catches writing the edge on top of copies that are still there, which makes a third."""
    store = Store()
    store.delete_does_nothing = True
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    with pytest.raises(ss.RepairAnomaly, match="paysim-tx-2"):
        _repair(store, _expected("paysim-tx-2"), apply=True)
    assert store.written == []


def test_an_id_this_load_does_not_write_is_left_alone() -> None:
    """Catches deleting a stored id the repair could not write again."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    report = _repair(store, _expected("paysim-tx-7"), apply=True)
    assert store.deleted == [] and store.written == []
    assert report.skipped and "paysim-tx-2" in report.skipped[0][0]


def test_copies_under_a_different_source_than_expected_are_left_alone() -> None:
    """Catches rewriting an edge whose stored copies point somewhere else than the dataset says."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"], source="elsewhere")
    report = _repair(store, _expected("paysim-tx-2"), apply=True)
    assert store.deleted == [] and report.skipped


def test_the_repair_stops_when_the_rewrite_itself_leaves_a_stray_and_touches_no_other() -> None:
    """The defect can hit the rewrite too. Catches carrying on past it."""
    store = Store()
    store.write_leaves_a_stray = True
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    store.add("paysim-tx-4", ["#1:4", "#1:7"], ["#1:4"])
    with pytest.raises(ss.RepairAnomaly, match="paysim-tx-2"):
        _repair(store, _expected("paysim-tx-2", "paysim-tx-4"), apply=True)
    assert "paysim-tx-4" not in store.written
    assert [c["rid"] for c in store.copies["paysim-tx-4"]] == ["#1:4", "#1:7"]


def test_the_repair_stops_when_the_written_edge_is_not_reached_from_its_source() -> None:
    """Catches trusting a record count alone: one stored record the traversal cannot reach is the
    same failure as the first stray, from the other side."""
    store = Store()
    store.write_is_not_linked = True
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    with pytest.raises(ss.RepairAnomaly, match="reaches 0"):
        _repair(store, _expected("paysim-tx-2"), apply=True)


def test_a_limit_repairs_that_many_ids_and_no_more() -> None:
    """The first real run is one id, to look at before the rest."""
    store = Store()
    for n in (2, 4, 6):
        store.add(f"paysim-tx-{n}", [f"#1:{n}", f"#1:{n + 1}"], [f"#1:{n}"])
    report = _repair(
        store, _expected("paysim-tx-2", "paysim-tx-4", "paysim-tx-6"), apply=True, limit=1
    )
    assert len(store.written) == 1 and len(report.written) == 1


def test_a_repaired_store_has_nothing_left_to_repair() -> None:
    """Catches a repair that is not idempotent: a second run must find nothing."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    _repair(store, _expected("paysim-tx-2"), apply=True)
    again = _repair(store, _expected("paysim-tx-2"), apply=True)
    assert again.planned == [] and store.written == ["paysim-tx-2"]


def test_missing_edges_are_written_and_present_ones_are_not_touched() -> None:
    """Catches a restore that rewrites what is there (a second record), and one that writes
    nothing: this is the step that gets back the edge the first repair lost."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    report = _restore(store, _expected("paysim-tx-1", "paysim-tx-2", "paysim-tx-3"), apply=True)
    assert store.written == ["paysim-tx-2", "paysim-tx-3"]
    assert report.written == ["paysim-tx-2", "paysim-tx-3"]
    assert len(store.copies["paysim-tx-1"]) == 1


def test_a_restore_dry_run_names_what_is_missing_and_writes_nothing() -> None:
    """Catches a dry run that writes, or one that says nothing about what is missing."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    report = _restore(store, _expected("paysim-tx-1", "paysim-tx-2"))
    assert store.written == [] and report.planned == [("paysim-tx-2", [])]
    assert "paysim-tx-2" in "\n".join(report.lines)  # type: ignore[attr-defined]


def test_a_restore_that_finds_nothing_missing_says_so() -> None:
    """Silence cannot be told from a restore that did not look."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    report = _restore(store, _expected("paysim-tx-1"), apply=True)
    assert report.planned == [] and any("nothing is missing" in line for line in report.lines)  # type: ignore[attr-defined]


def test_a_restore_looks_at_every_stored_id_not_only_the_first_page() -> None:
    """Catches a restore that reads one page of ids and calls the rest missing (it would write
    thirteen thousand duplicates)."""
    store = Store()
    ids = [f"paysim-tx-{n:03d}" for n in range(12)]
    for i in ids:
        store.add(i, [f"#1:{i[-3:]}"], [f"#1:{i[-3:]}"])
    report = _run(
        ss.restore_missing_edges(
            store,
            edge_type=TYPE,
            prefix=PREFIX,
            expected=_expected(*ids),
            rewrite=_rewriter(store),
            say=lambda _l: None,
            apply=True,
            page=5,
        )
    )
    assert report.planned == [] and store.written == []


def test_a_restore_stops_when_the_written_edge_is_not_reached() -> None:
    """Catches a restore that reports success on a record the source cannot reach."""
    store = Store()
    store.write_is_not_linked = True
    with pytest.raises(ss.RepairAnomaly, match="paysim-tx-2"):
        _restore(store, _expected("paysim-tx-2"), apply=True)


def test_a_restore_limit_writes_that_many_and_no_more() -> None:
    """The first real write is one edge, to look at."""
    store = Store()
    report = _restore(store, _expected("paysim-tx-1", "paysim-tx-2"), apply=True, limit=1)
    assert len(store.written) == 1 and len(report.written) == 1


def test_ids_stored_that_the_dataset_does_not_write_are_reported_and_not_touched() -> None:
    """Catches a restore that deletes, or says nothing about, rows it did not expect."""
    store = Store()
    store.add("paysim-tx-9", ["#1:9"], ["#1:9"])
    report = _restore(store, _expected("paysim-tx-1"), apply=True)
    assert store.deleted == [] and "paysim-tx-9" in "\n".join(report.lines)  # type: ignore[attr-defined]


def test_the_post_load_check_says_loudly_how_many_and_what_to_run() -> None:
    """Catches a check that passes when ids are stored twice, or says so without the way out."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    lines: list[str] = []
    n = _run(
        ss.report_ids_stored_twice(
            store, edge_types=[TYPE], prefix=PREFIX, say=lines.append, advice="DO-THIS"
        )
    )
    assert n == 1
    text = "\n".join(lines)
    assert "1" in text and "stored more than once" in text and "DO-THIS" in text
    # No repair exists any more (ADR-056 Amendment 19): the line must not send anyone to one.
    assert "remove the strays" not in text and "--repair-strays" not in text


def test_the_post_load_check_is_quiet_about_a_clean_graph_but_still_says_so() -> None:
    """A check that prints nothing when it passes cannot be told from one that did not run."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    lines: list[str] = []
    n = _run(
        ss.report_ids_stored_twice(
            store, edge_types=[TYPE], prefix=PREFIX, say=lines.append, advice="x"
        )
    )
    assert n == 0 and any("no id stored more than once" in line for line in lines)
