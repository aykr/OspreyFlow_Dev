"""`GraphArcadeDBAdapter.strip_provenance_references` (ADR-124 decision 11, U10), without a store:
what it reads, what it writes, that it filters nothing out (superseded and reverted links are
rewritten too), that it pages, and that a second run changes nothing. The same behaviour against
ArcadeDB is `tests/conformance/graph_port/test_suite.py`."""

from __future__ import annotations

import copy
from typing import Any, cast

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter, _without_references
from ontology.handling import load_uk_le_scheme

_TYPES_SQL = "SELECT name, type, indexes FROM schema:types"


def _source(document_id: str) -> dict[str, Any]:
    return {"document_id": document_id, "locator": "p.1", "excerpt_hash": "a" * 64}


def _row(link_id: str, *documents: str, superseded: bool = False) -> dict[str, Any]:
    return {
        "id": link_id,
        "audit": {"superseded_by": "next" if superseded else None},
        "provenance": {
            "state": "asserted",
            "sources": [_source(d) for d in documents],
            "first_seen": "2026-01-01T00:00:00+00:00",
        },
    }


class _Client:
    """Stands in for ArcadeDB: one link type holding `rows`, paged by `id`, which answers a
    `SELECT` and applies an `UPDATE ... SET provenance` by id. It honours a filter on
    `superseded_by` or `reverted` if the adapter adds one, as the real store would."""

    def __init__(self, rows: list[dict[str, Any]], types: int = 1) -> None:
        self.rows = {f"mx_T{i}": copy.deepcopy(rows) for i in range(types)}
        self.commands: list[str] = []

    async def sql(self, command: str, *, params: Any = None, **_: Any) -> list[dict[str, Any]]:
        if command == _TYPES_SQL:
            return [
                {"name": name, "type": "edge", "indexes": [{"unique": True, "properties": ["id"]}]}
                for name in self.rows
            ]
        # What ArcadeDB refused (24 October 2026, live): a bound parameter named like a keyword
        # (`:after`) is a parse error, so the stand-in refuses it too.
        for name in params or {}:
            if name in {"after", "before", "from", "where", "order", "select", "limit", "skip"}:
                raise ValueError(f"SQL syntax error: no viable alternative at input {name!r}")
        self.commands.append(command)
        name = command.split("`")[1]
        if command.startswith("SELECT"):
            after = params["after_id"]
            limit = int(command.rsplit("LIMIT ", 1)[1])
            rows = sorted((r for r in self.rows[name] if r["id"] > after), key=lambda r: r["id"])
            if "superseded_by" in command:
                rows = [r for r in rows if r["audit"]["superseded_by"] is None]
            return [{"id": r["id"], "provenance": r["provenance"]} for r in rows[:limit]]
        for r in self.rows[name]:
            if r["id"] == params["id"]:
                r["provenance"] = params["provenance"]
        return []


def _adapter(client: _Client) -> GraphArcadeDBAdapter:
    return GraphArcadeDBAdapter(cast(Any, client), load_uk_le_scheme())


def _documents(client: _Client, link_id: str, type_name: str = "mx_T0") -> list[str]:
    (row,) = [r for r in client.rows[type_name] if r["id"] == link_id]
    return [s["document_id"] for s in row["provenance"]["sources"]]


def test_a_source_with_the_prefix_is_removed_and_nothing_else_of_the_provenance() -> None:
    provenance = _row("l1", "doc-1", "manual:change:old", "manual:change")["provenance"]
    stripped = _without_references(provenance, "manual:change:")
    assert stripped is not None
    assert [s["document_id"] for s in stripped["sources"]] == ["doc-1", "manual:change"]
    assert stripped["state"] == "asserted" and stripped["first_seen"] == provenance["first_seen"]


def test_a_provenance_with_no_such_source_gives_nothing_to_write() -> None:
    assert _without_references(_row("l1", "doc-1")["provenance"], "manual:change:") is None
    assert _without_references(None, "manual:change:") is None
    assert _without_references({"sources": "odd"}, "manual:change:") is None


async def test_it_rewrites_superseded_links_as_well_as_live_ones_and_counts_each_link() -> None:
    client = _Client(
        [
            _row("l1", "doc-1", "manual:change:first", superseded=True),
            _row("l2", "doc-1", "manual:change:l1"),
            _row("l3", "doc-1"),
        ]
    )
    assert await _adapter(client).strip_provenance_references("manual:change:") == 2
    assert _documents(client, "l1") == ["doc-1"], "the superseded link too"
    assert _documents(client, "l2") == ["doc-1"]
    assert _documents(client, "l3") == ["doc-1"]
    select = [c for c in client.commands if c.startswith("SELECT")][0]
    for refused in ("superseded", "reverted"):
        assert refused not in select, "the scan filters nothing out"


async def test_each_prefix_is_its_own_call_and_the_other_is_left_alone() -> None:
    client = _Client([_row("l1", "doc-1", "manual:remove-picture:old", "manual:change:first")])
    adapter = _adapter(client)
    assert await adapter.strip_provenance_references("manual:change:") == 1
    assert _documents(client, "l1") == ["doc-1", "manual:remove-picture:old"]
    assert await adapter.strip_provenance_references("manual:remove-picture:") == 1
    assert _documents(client, "l1") == ["doc-1"]


async def test_a_second_run_changes_nothing_and_returns_zero() -> None:
    client = _Client([_row("l1", "doc-1", "manual:change:first")])
    adapter = _adapter(client)
    assert await adapter.strip_provenance_references("manual:change:") == 1
    writes = [c for c in client.commands if c.startswith("UPDATE")]
    assert await adapter.strip_provenance_references("manual:change:") == 0
    assert [c for c in client.commands if c.startswith("UPDATE")] == writes


async def test_it_reads_every_page_and_every_link_type() -> None:
    rows = [_row(f"l{n:05d}", "doc-1", "manual:change:old") for n in range(1203)]
    client = _Client(rows, types=2)
    assert await _adapter(client).strip_provenance_references("manual:change:") == 2 * 1203
    for type_name in client.rows:
        assert all(_documents(client, r["id"], type_name) == ["doc-1"] for r in rows)
