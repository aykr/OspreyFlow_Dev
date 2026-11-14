"""ADR-124 Amendment 18: a write call's lookups are counted, not timed.

The write path resolves the ids a call touches by SQL through each vertex type's unique `id` index.
Asked of every vertex type in the store, a call cost one read of the store's types and one query per
type, T, however few types it wrote: the cost of a per-row load (one call a row: the CLI, the site
grid, the seeders) grew with the store's types. A link write now asks only the types its link type
joins (an end missed there is asked again of every type). A node write still asks every type,
once per call, so that an id another type holds is refused rather than inserted beside it as a
second vertex under one id. These cases pin the counts, which are deterministic where a time is
not (rule 14: a timing bound run without a lease measures nothing).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from adapters.graph_arcadedb.lookup import IdInTwoTypes, vertex_records
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.errors import OntologyError

from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter, make_edge
from tests.adapters.graph_arcadedb.test_write_onto_a_reverted_node import NodeStore, _adapter, _write

LOOKUP = re.compile(r"SELECT @rid AS rid, id FROM `(\w+)` WHERE id IN :ids")
INDEXED = [{"unique": True, "properties": ["id"]}]
OTHER_TYPES = [f"Other{n}" for n in range(30)]


def _with_types(rows: list[dict[str, Any]], extra: int) -> list[dict[str, Any]]:
    return rows + [
        {"name": physical_type_name(name), "type": "vertex", "indexes": INDEXED}
        for name in OTHER_TYPES[:extra]
    ]


class ManyTypedNodes(NodeStore):
    """`NodeStore` whose store holds `extra` more vertex types, each with its unique `id` index."""

    def __init__(self, extra: int, other: frozenset[str] = frozenset()) -> None:
        super().__init__()
        self.extra = extra
        #: Ids held by a vertex of `Other0`, not a `Person`.
        self.other = other

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        lookup = LOOKUP.fullmatch(command)
        if lookup is not None and lookup.group(1) == physical_type_name("Other0"):
            assert params is not None
            self.sql_sent.append(command)
            return [{"rid": f"#7:{n}", "id": i} for n, i in enumerate(params["ids"]) if i in self.other]
        rows = await super().sql(command, params=params, session_id=session_id)
        if command.startswith("SELECT name, type, indexes FROM schema:types"):
            return _with_types(rows, self.extra)
        if lookup is not None:
            return rows if lookup.group(1) == physical_type_name("Person") else []
        return rows


class ManyTypedLinks(CountingStore):
    """`CountingStore` whose store holds `extra` more vertex types; `elsewhere` holds ids stored as
    a `Person`, a type `TRANSACTED` does not join."""

    def __init__(self, extra: int, elsewhere: frozenset[str] = frozenset()) -> None:
        super().__init__()
        self.extra = extra
        self.elsewhere = elsewhere

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        lookup = LOOKUP.fullmatch(command)
        if command == "SELECT name, type, indexes FROM schema:types":
            rows = await super().sql(command, params=params, session_id=session_id)
            person = {"name": physical_type_name("Person"), "type": "vertex", "indexes": INDEXED}
            return _with_types([*rows, person], self.extra)
        if lookup is not None and params is not None:
            self.sql_sent.append((command, dict(params)))
            if lookup.group(1) == physical_type_name("Person"):
                return [{"rid": self.vertex_rid(i), "id": i} for i in params["ids"] if i in self.elsewhere]
            if lookup.group(1) == physical_type_name("Endpoint"):
                return [
                    {"rid": self.vertex_rid(i), "id": i}
                    for i in params["ids"]
                    if i not in self.elsewhere
                ]
            return []
        return await super().sql(command, params=params, session_id=session_id)


def _lookups(sent: list[Any]) -> list[str]:
    commands = [c if isinstance(c, str) else c[0] for c in sent]
    return [m.group(1) for c in commands if (m := LOOKUP.fullmatch(c)) is not None]


def _type_reads(sent: list[Any]) -> int:
    commands = [c if isinstance(c, str) else c[0] for c in sent]
    return sum(1 for c in commands if c.startswith("SELECT name, type, indexes FROM schema:types"))


@pytest.mark.parametrize("extra", [0, 30])
def test_a_node_write_asks_every_type_once_a_call(extra: int) -> None:
    """One read of the store's types and one query per indexed vertex type, for the whole call,
    however many nodes it writes."""
    store = ManyTypedNodes(extra)
    graph = _adapter(store)
    writes = [
        _write(f"n-{n}", classification="OFFICIAL", load_id="l", datasets=["Z2001ZZ"], source="f")
        for n in range(3)
    ]
    asyncio.run(graph.upsert_nodes(writes, "tx"))
    assert _type_reads(store.sql_sent) == 1
    assert sorted(_lookups(store.sql_sent)) == sorted(
        [physical_type_name("Person")] + [physical_type_name(t) for t in OTHER_TYPES[:extra]]
    )


def _writes(store: ManyTypedNodes) -> list[str]:
    return [c for c in store.sql_sent if c.startswith(("INSERT", "UPDATE"))]


def test_a_node_write_onto_an_id_another_type_holds_is_refused_and_the_call_writes_nothing() -> None:
    """Never a second vertex under one id. The refusal is found before the call's first write is
    sent, so the node before it in the call is not written either; and it names neither type, since
    the holder may be a node the writer cannot read (rule 3)."""
    store = ManyTypedNodes(1, other=frozenset({"n-2"}))
    graph = _adapter(store)
    writes = [
        _write(f"n-{n}", classification="OFFICIAL", load_id="l", datasets=["Z2001ZZ"], source="f")
        for n in (1, 2)
    ]
    with pytest.raises(OntologyError, match="held by a node of another type") as refused:
        asyncio.run(graph.upsert_nodes(writes, "tx"))
    assert "Other0" not in str(refused.value) and "Person" not in str(refused.value)
    assert _writes(store) == []


def test_one_call_writing_one_id_as_two_types_is_refused_and_writes_nothing() -> None:
    """An id new to the store, written twice in one call under two types, is refused before either
    write: the second would otherwise be looked for in its own type alone, found nowhere, and
    inserted beside the first."""
    store = ManyTypedNodes(0)
    graph = _adapter(store)
    first = _write("n-1", classification="OFFICIAL", load_id="l", datasets=["Z2001ZZ"], source="f")
    second = first.model_copy(update={"type": "Organisation", "properties": {"name": "Acme"}})
    with pytest.raises(OntologyError, match="held by a node of another type"):
        asyncio.run(graph.upsert_nodes([first, second], "tx"))
    assert _writes(store) == []


@pytest.mark.parametrize("extra", [0, 30])
def test_a_link_write_asks_only_the_types_its_link_joins(extra: int) -> None:
    store = ManyTypedLinks(extra)
    graph = make_adapter(store)
    asyncio.run(graph.upsert_edges([make_edge("a", "b", 1), make_edge("b", "c", 2)], "tx"))
    assert _type_reads(store.sql_sent) == 1
    # TRANSACTED joins Asset and Endpoint; this store indexes Endpoint alone of the two.
    assert _lookups(store.sql_sent) == [physical_type_name("Endpoint")]


def test_an_end_of_a_type_the_link_does_not_join_is_refused_for_its_type_not_missing() -> None:
    """An end the narrow question misses is asked of every type, so a link to a node of the wrong
    type is refused for that, as before, never reported as a node that does not exist."""
    store = ManyTypedLinks(0, elsewhere=frozenset({"p"}))
    graph = make_adapter(store)
    with pytest.raises(OntologyError) as refused:
        asyncio.run(graph.upsert_edges([make_edge("a", "p", 1)], "tx"))
    assert "does not exist" not in str(refused.value)
    assert "Person" in str(refused.value)


def test_one_id_held_by_two_types_stops_the_write() -> None:
    class Twice:
        async def sql(self, command: str, **_: Any) -> list[dict[str, Any]]:
            if command.startswith("SELECT name, type, indexes"):
                return [
                    {"name": physical_type_name(t), "type": "vertex", "indexes": INDEXED}
                    for t in ("Person", "Endpoint")
                ]
            n = 1 if physical_type_name("Person") in command else 2
            return [{"rid": f"#{n}:0", "id": "x"}]

    with pytest.raises(IdInTwoTypes):
        asyncio.run(vertex_records(Twice(), ["x"]))
