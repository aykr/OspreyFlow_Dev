"""Stray edge records, and removing them (ADR-056 Amendments 9 to 16).

Seen, 1 October 2026: ArcadeDB stored a few edges twice during a load (13,076 records for 13,068
written). A traversal reaches each such edge once; the second record is a stray that only a scan
sees. It inflates every scan-based count, including the adapter's corpus total behind edge weights.
The repair keeps the record the source vertex reaches and removes the other, one id at a time,
dry run first, and stops at the first surprise, because it deletes records and the only way back is
a reload. Each test names what it would catch. The store is a fake that answers the same questions
the real one is asked; the delete itself was not shown against a real ArcadeDB here.
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
    """Edge records by id: every stored copy, and which record each source's edge list reaches."""

    def __init__(self) -> None:
        self.copies: dict[str, list[dict[str, str]]] = {}
        self.reachable: dict[str, list[str]] = {}
        self.deleted: list[str] = []
        self.statements: list[str] = []
        #: Deleting a record also unlinks the record the source reached (the dangerous behaviour).
        self.delete_unlinks_the_real_one = False
        self.reachable_answer_is_unusable = False

    def add(self, edge_id: str, rids: list[str], reached: list[str], source: str = "a") -> None:
        self.copies[edge_id] = [{"rid": r, "id": edge_id, "source": source} for r in rids]
        self.reachable[edge_id] = list(reached)

    async def sql(self, command: str, *, params: Any = None, session_id: Any = None) -> list[Any]:
        self.statements.append(command)
        if "GROUP BY id" in command:
            return [{"id": i, "n": len(c)} for i, c in self.copies.items()]
        if command.startswith("SELECT @rid AS rid"):
            wanted = re.search(r"LIKE '([^']*)'", command)
            assert wanted
            return list(self.copies.get(wanted.group(1), []))
        if command.startswith("DELETE FROM"):
            rid = re.search(r"@rid = (#\d+:\d+)", command)
            assert rid, command
            self.deleted.append(rid.group(1))
            for edge_id, copies in self.copies.items():
                self.copies[edge_id] = [c for c in copies if c["rid"] != rid.group(1)]
                if self.delete_unlinks_the_real_one and len(copies) != len(self.copies[edge_id]):
                    self.reachable[edge_id] = []
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
        if self.reachable_answer_is_unusable:
            return [{"result": "?"}]
        return [{"result": r} for r in reached]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _repair(store: Store, **kw: Any) -> ss.RepairReport:
    lines: list[str] = []
    kw.setdefault("apply", False)
    report: ss.RepairReport = _run(
        ss.repair_ids_stored_twice(store, edge_type=TYPE, prefix=PREFIX, say=lines.append, **kw)
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


def test_a_dry_run_changes_nothing_and_says_what_it_would_remove() -> None:
    """Catches a repair that deletes without being told to, or reports nothing to review."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    report = _repair(store)
    assert store.deleted == []
    assert report.planned == [("paysim-tx-2", "#1:2", ["#1:9"])]
    assert any("#1:9" in line and "would remove" in line for line in report.lines)  # type: ignore[attr-defined]


def test_the_copy_the_source_reaches_is_kept_whichever_comes_first() -> None:
    """Catches keeping the first or the lowest record, which in half the cases is the stray."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:9"])
    _repair(store, apply=True)
    assert store.deleted == ["#1:2"]
    assert [c["rid"] for c in store.copies["paysim-tx-2"]] == ["#1:9"]


def test_nothing_is_deleted_when_the_reachable_record_cannot_be_identified() -> None:
    """Catches deleting on a guess: the traversal's answer is not one of the stored records."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:9"])
    store.reachable_answer_is_unusable = True
    report = _repair(store, apply=True)
    assert store.deleted == []
    assert report.skipped and "paysim-tx-2" in report.skipped[0][0]


def test_nothing_is_deleted_when_the_source_reaches_neither_copy() -> None:
    """Catches removing both records of an edge nothing links to."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], [])
    report = _repair(store, apply=True)
    assert store.deleted == []
    assert report.skipped


def test_the_repair_stops_at_the_first_edge_that_loses_its_link_and_touches_no_other() -> None:
    """Catches carrying on after a delete took the real edge with it: it must stop, say so, and
    leave every later id alone."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    store.add("paysim-tx-4", ["#1:4", "#1:7"], ["#1:4"])
    store.delete_unlinks_the_real_one = True
    with pytest.raises(ss.RepairAnomaly, match="paysim-tx-2"):
        _repair(store, apply=True)
    assert store.deleted == ["#1:9"]


def test_a_limit_repairs_that_many_ids_and_no_more() -> None:
    """The first real run is one id, to look at before the rest."""
    store = Store()
    for n in (2, 4, 6):
        store.add(f"paysim-tx-{n}", [f"#1:{n}", f"#1:{n + 1}"], [f"#1:{n}"])
    report = _repair(store, apply=True, limit=1)
    assert store.deleted == ["#1:3"] or store.deleted == ["#1:5"] or store.deleted == ["#1:7"]
    assert len(store.deleted) == 1 and report.removed == 1


def test_a_repaired_store_has_nothing_left_to_repair() -> None:
    """Catches a repair that is not idempotent: a second run must find nothing."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    _repair(store, apply=True)
    again = _repair(store, apply=True)
    assert again.planned == [] and store.deleted == ["#1:9"]


def test_the_delete_names_the_record_and_the_type_not_the_id() -> None:
    """Catches `DELETE ... WHERE id = ...`, which would remove both copies."""
    store = Store()
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    _repair(store, apply=True)
    (delete,) = [s for s in store.statements if s.startswith("DELETE")]
    assert delete == f"DELETE FROM {TYPE} WHERE @rid = #1:9"


def test_the_post_load_check_says_loudly_how_many_and_what_to_run() -> None:
    """Catches a check that passes when ids are stored twice, or says so without the way out."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    store.add("paysim-tx-2", ["#1:2", "#1:9"], ["#1:2"])
    lines: list[str] = []
    n = _run(
        ss.report_ids_stored_twice(
            store, edge_types=[TYPE], prefix=PREFIX, say=lines.append, repair_command="RUN-THIS"
        )
    )
    assert n == 1
    text = "\n".join(lines)
    assert "1" in text and "stored more than once" in text and "RUN-THIS" in text


def test_the_post_load_check_is_quiet_about_a_clean_graph_but_still_says_so() -> None:
    """A check that prints nothing when it passes cannot be told from one that did not run."""
    store = Store()
    store.add("paysim-tx-1", ["#1:1"], ["#1:1"])
    lines: list[str] = []
    n = _run(
        ss.report_ids_stored_twice(
            store, edge_types=[TYPE], prefix=PREFIX, say=lines.append, repair_command="x"
        )
    )
    assert n == 0 and any("no id stored more than once" in line for line in lines)
