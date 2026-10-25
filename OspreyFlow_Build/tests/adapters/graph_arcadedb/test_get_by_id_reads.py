"""The two reads by id (ADR-124 U1), without a store: what is sent, how the ids are chunked, how
the ids reach the SQL, what is refused before any query goes out, and how rows are merged and
ordered. What the adapter returns for a hidden, superseded or absent id is the conformance suite's
to prove, against ArcadeDB."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

import pytest

from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter, _id_chunks
from adapters.graph_arcadedb.builders import (
    render_get_edges_gremlin,
    render_get_nodes_gremlin,
    render_record_id_lookup_sql,
)
from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"])


_NOW = "2026-01-01T00:00:00+00:00"


def _rid(identifier: str) -> str:
    """A record id for an id of the form `n00012`: `#9:12`."""
    return f"#9:{int(identifier[1:])}"


def _id_of(rid: str) -> str:
    return f"n{int(rid.split(':')[1]):05d}"


def _element_map(identifier: str, *, edge: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": identifier,
        "label": "mx_ASSOCIATE_OF" if edge else "mx_Person",
        "provenance": {
            "state": "asserted",
            "sources": [{"document_id": "d", "locator": "l", "excerpt_hash": "a" * 64}],
            "first_seen": _NOW,
        },
        "handling": {
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "u",
            "owning_unit": "u",
        },
        "audit": {"created_at": _NOW, "created_by": "t"},
    }
    if edge:
        record.update(source="n00000", target="n00001")
    return record


_TYPES_SQL = "SELECT name, type, indexes FROM schema:types"


def _index(*properties: str, unique: bool = True) -> dict[str, Any]:
    """An entry of a type's `indexes` in ArcadeDB's `schema:types` answer."""
    return {
        "name": f"T[{','.join(properties)}]",
        "typeName": "T",
        "unique": unique,
        "properties": list(properties),
    }


def _stored(name: str, kind: str, *indexes: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "type": kind, "indexes": list(indexes)}


def _default_types() -> list[dict[str, Any]]:
    """What the store holds: every type of the default ontology, each with the unique `id` index,
    a type another process added since (a proposal's own storage type, an entity type), a type of
    the other kind carrying the same index, and `SOME_DOCUMENT`, which is neither."""
    ontology = load_default_ontology()
    return [
        *(_stored(f"mx_{e.name}", "vertex", _index("id")) for e in ontology.entity_types),
        *(_stored(f"mx_{e.name}", "edge", _index("id")) for e in ontology.edge_types),
        _stored("mx_Boat", "vertex", _index("id"), _index("hull", unique=False)),
        _stored("mx_KNOWN_TO__01JP", "edge", _index("id")),
        _stored("Plain", "document", _index("id")),
    ]


class _Client:
    """Stands in for ArcadeDB. `known` is the ids the store holds: SQL answers with the record id
    of each one asked for, and Gremlin answers with the element maps of the record ids asked for,
    in descending order and each twice (a stray second record, ADR-056 Amendments 15 and 19), so
    the adapter's own ordering and merging are what a test sees. `types` is the answer to
    `schema:types`. It keeps what it was sent."""

    def __init__(
        self,
        known: Callable[[str], bool] = lambda _id: True,
        types: list[dict[str, Any]] | None = None,
    ) -> None:
        self.known = known
        self.types = _default_types() if types is None else types
        self.schema_sent = 0
        self.sql_sent: list[tuple[str, dict[str, Any]]] = []
        self.gremlin_sent: list[str] = []

    async def sql(self, command: str, *, params: Any = None, **_: Any) -> list[dict[str, Any]]:
        if command == _TYPES_SQL:
            self.schema_sent += 1
            return self.types
        self.sql_sent.append((command, dict(params or {})))
        return [{"rid": _rid(i)} for i in (params or {}).get("ids", []) if self.known(i)]

    async def gremlin(self, query: str, **_: Any) -> list[dict[str, Any]]:
        self.gremlin_sent.append(query)
        rids = re.findall(r"'(#\d+:\d+)'", query.split("])")[0])
        ids = sorted((_id_of(r) for r in rids), reverse=True)
        edge = query.startswith("g.E(")
        return [_element_map(i, edge=edge) for i in ids for _ in (0, 1)]


def _adapter(client: _Client | None = None) -> tuple[GraphArcadeDBAdapter, _Client]:
    """An adapter that has applied no ontology: these reads do not depend on one."""
    client = client or _Client()
    return GraphArcadeDBAdapter(cast(Any, client), load_uk_le_scheme()), client


def _asked(client: _Client) -> set[str]:
    """The stored types the id lookups named, unquoted."""
    names = (re.search(r"FROM `([^`]+)` WHERE", c) for c, _ in client.sql_sent)
    return {m.group(1) for m in names if m}


# --- the literal -------------------------------------------------------------------------------


def test_a_line_feed_in_a_value_is_escaped_not_sent_raw() -> None:
    assert groovy_string_literal("a\nb") == "'a\\nb'"


def test_a_carriage_return_in_a_value_is_escaped_not_sent_raw() -> None:
    assert groovy_string_literal("a\rb") == "'a\\rb'"


def test_a_backslash_before_an_n_is_still_a_backslash_and_an_n() -> None:
    """The backslash is escaped first, so a value holding a backslash and an `n` does not become
    a line feed."""
    assert groovy_string_literal("a\\nb") == "'a\\\\nb'"


def test_a_quote_is_still_escaped() -> None:
    assert groovy_string_literal("o'b") == "'o\\'b'"


@pytest.mark.parametrize("render", [render_get_nodes_gremlin, render_get_edges_gremlin])
def test_an_id_with_a_line_break_renders_on_one_line(render: Any) -> None:
    query = render(["a\nb", "c\rd"], AccessFilter(load_uk_le_scheme()), READER)
    assert "\n" not in query and "\r" not in query
    assert "'a\\nb'" in query and "'c\\rd'" in query


# --- what is refused before a query is sent ----------------------------------------------------


async def test_get_nodes_refuses_a_bare_string_for_the_ids() -> None:
    """A `str` is a `Sequence[str]` of characters: `get_nodes("abc")` would look up three ids."""
    adapter, client = _adapter()
    with pytest.raises(TypeError):
        await adapter.get_nodes("n00001", READER)
    assert client.sql_sent == [] and client.gremlin_sent == []


async def test_get_edges_refuses_a_bare_string_for_the_ids() -> None:
    adapter, client = _adapter()
    with pytest.raises(TypeError):
        await adapter.get_edges("n00001", READER)
    assert client.sql_sent == [] and client.gremlin_sent == []


async def test_get_nodes_and_get_edges_of_no_ids_send_no_query() -> None:
    adapter, client = _adapter()
    assert await adapter.get_nodes([], READER) == []
    assert await adapter.get_edges([], READER) == []
    assert client.sql_sent == [] and client.gremlin_sent == [] and client.schema_sent == 0


# --- chunking ----------------------------------------------------------------------------------


def test_2501_ids_give_chunks_of_1000_1000_and_501() -> None:
    chunks = _id_chunks([f"id-{i:05d}" for i in range(2501)])
    assert [len(c) for c in chunks] == [1000, 1000, 501]
    assert [i for c in chunks for i in c] == [f"id-{i:05d}" for i in range(2501)]


def test_no_ids_give_no_chunks() -> None:
    assert _id_chunks([]) == []


def test_exactly_one_chunk_of_ids_is_one_chunk_and_one_more_is_two() -> None:
    assert [len(c) for c in _id_chunks([str(i) for i in range(1000)])] == [1000]
    assert [len(c) for c in _id_chunks([str(i) for i in range(1001)])] == [1000, 1]


def test_a_repeated_id_is_dropped_wherever_it_falls_in_the_order_given() -> None:
    ids = ["x", *(str(i) for i in range(1500)), "x"]
    chunks = _id_chunks(ids)
    assert sum(c.count("x") for c in chunks) == 1
    assert [len(c) for c in chunks] == [1000, 501]


async def test_the_adapter_resolves_and_reads_once_per_chunk() -> None:
    adapter, client = _adapter()
    nodes = await adapter.get_nodes([f"n{i:05d}" for i in range(2501)], READER)
    assert len(client.gremlin_sent) == 3
    assert len(nodes) == 2501
    client.gremlin_sent.clear()
    await adapter.get_edges([f"n{i:05d}" for i in range(1001)], READER)
    assert len(client.gremlin_sent) == 2


# --- how the ids reach the store ---------------------------------------------------------------


async def test_ids_reach_the_sql_as_a_parameter_never_inside_the_command() -> None:
    awkward = "n00001' OR 1=1 --\nx\\"
    adapter, client = _adapter(_Client(known=lambda _id: False))
    await adapter.get_nodes([awkward], READER)
    await adapter.get_edges([awkward], READER)
    assert client.sql_sent
    for command, params in client.sql_sent:
        assert "OR 1=1" not in command and "n00001" not in command
        assert params == {"ids": [awkward]}
        assert command.endswith("WHERE id IN :ids")


async def test_each_read_asks_every_type_of_its_kind_the_store_holds() -> None:
    """The types come from the store, not from this process's ontology: a type another process
    added since (`mx_Boat`, a proposal's `mx_KNOWN_TO__01JP`) is asked too."""
    ontology = load_default_ontology()
    adapter, client = _adapter()
    await adapter.get_nodes(["n00001"], READER)
    assert _asked(client) == {f"mx_{e.name}" for e in ontology.entity_types} | {"mx_Boat"}
    client.sql_sent.clear()
    await adapter.get_edges(["n00001"], READER)
    assert _asked(client) == {f"mx_{e.name}" for e in ontology.edge_types} | {"mx_KNOWN_TO__01JP"}


async def test_the_store_is_asked_for_its_types_once_per_call_not_once_per_chunk() -> None:
    adapter, client = _adapter()
    await adapter.get_nodes([f"n{i:05d}" for i in range(2501)], READER)
    assert client.schema_sent == 1
    await adapter.get_edges([f"n{i:05d}" for i in range(2501)], READER)
    assert client.schema_sent == 2


async def test_a_type_without_a_unique_index_on_exactly_id_is_not_asked() -> None:
    """Asking such a type would scan it: only a type whose `id` is answered from a unique index
    on `id` alone is looked in. A type of the wrong kind is not asked either."""
    types = [
        _stored("mx_Good", "vertex", _index("id")),
        _stored("mx_NoIndex", "vertex"),
        _stored("mx_NotUnique", "vertex", _index("id", unique=False)),
        _stored("mx_OtherProperty", "vertex", _index("handling_code")),
        _stored("mx_Composite", "vertex", _index("id", "handling_code")),
        _stored("mx_GoodLink", "edge", _index("id")),
        _stored("mx_LinkNoIndex", "edge", _index("handling_code")),
    ]
    adapter, client = _adapter(_Client(types=types))
    await adapter.get_nodes(["n00001"], READER)
    assert _asked(client) == {"mx_Good"}
    client.sql_sent.clear()
    await adapter.get_edges(["n00001"], READER)
    assert _asked(client) == {"mx_GoodLink"}


async def test_nodes_never_ask_a_link_type_and_links_never_ask_a_vertex_type() -> None:
    types = [_stored("mx_V", "vertex", _index("id")), _stored("mx_E", "edge", _index("id"))]
    adapter, client = _adapter(_Client(types=types))
    await adapter.get_nodes(["n00001"], READER)
    assert _asked(client) == {"mx_V"}
    client.sql_sent.clear()
    await adapter.get_edges(["n00001"], READER)
    assert _asked(client) == {"mx_E"}


async def test_a_type_with_a_double_underscore_name_is_quoted_in_the_sql() -> None:
    adapter, client = _adapter(_Client(types=[_stored("mx_KNOWN_TO__01JP", "edge", _index("id"))]))
    await adapter.get_edges(["n00001"], READER)
    assert client.sql_sent[0][0] == ("SELECT @rid AS rid FROM `mx_KNOWN_TO__01JP` WHERE id IN :ids")


async def test_a_type_name_that_is_not_a_plain_identifier_is_refused() -> None:
    bad = [_stored("mx_V; DROP TYPE mx_V", "vertex", _index("id"))]
    adapter, client = _adapter(_Client(types=bad))
    with pytest.raises(ValueError):
        await adapter.get_nodes(["n00001"], READER)
    assert client.sql_sent == []


async def test_no_types_means_no_rows_and_only_the_empty_read() -> None:
    adapter, client = _adapter(_Client(types=[]))
    assert await adapter.get_nodes(["n00001"], READER) == []
    assert client.sql_sent == []
    assert len(client.gremlin_sent) == 1 and "limit(0)" in client.gremlin_sent[0]


@pytest.mark.parametrize("which", ["types", "lookup"])
async def test_an_error_from_the_store_is_raised_whatever_it_says(which: str) -> None:
    """Including the words ArcadeDB uses for a type it lacks: only types the store listed are
    asked, so there is no missing type to read as no rows, and an error is never an empty answer."""
    from adapters.graph_arcadedb.client import ArcadeDBError

    class Failing(_Client):
        async def sql(self, command: str, **kw: Any) -> list[dict[str, Any]]:
            if (command == _TYPES_SQL) == (which == "types"):
                raise ArcadeDBError(
                    "ArcadeDB error 500: Type with name 'mx_Person' was not found",
                    status_code=500,
                    exception_class="com.arcadedb.exception.SchemaException",
                )
            return await super().sql(command, **kw)

    adapter, _ = _adapter(Failing())
    with pytest.raises(ArcadeDBError):
        await adapter.get_nodes(["n00001"], READER)


async def test_a_record_id_that_is_not_a_record_id_is_refused_before_it_reaches_gremlin() -> None:
    class Odd(_Client):
        async def sql(self, command: str, **kw: Any) -> list[dict[str, Any]]:
            if command == _TYPES_SQL:
                return await super().sql(command, **kw)
            return [{"rid": "#1:0']).drop()//"}]

    adapter, client = _adapter(Odd())
    with pytest.raises(ValueError):
        await adapter.get_nodes(["n00001"], READER)
    assert client.gremlin_sent == []


# --- an empty list of record ids ---------------------------------------------------------------


def test_the_gremlin_builders_never_render_an_empty_id_list_as_every_element() -> None:
    """`g.V([])` may be every vertex (the empty form of `g.V()`), so an empty list is never
    rendered as an id list: it is a traversal that yields nothing, with the same access step and
    projection as the one for ids, and no `g.V()`/`g.E()` that reads the whole store."""
    access = AccessFilter(load_uk_le_scheme())
    has_access = access.gremlin_has_step(READER)
    nodes = render_get_nodes_gremlin([], access, READER)
    edges = render_get_edges_gremlin([], access, READER)
    assert nodes == f"g.V().limit(0).{has_access}.elementMap()"
    assert edges == (
        f"g.E().limit(0).{has_access}"
        f".where(outV().{has_access}).where(inV().{has_access}).elementMap()"
    )


async def test_ids_the_store_does_not_hold_still_send_the_gremlin_read() -> None:
    """A guessed id that is absent must cost what a hidden one costs (a hidden id resolves, so
    its Gremlin read runs and filters it): under `/seed` the round trips would otherwise be a
    membership test."""
    adapter, client = _adapter(_Client(known=lambda _id: False))
    assert await adapter.get_nodes(["n00001", "n00002"], READER) == []
    assert await adapter.get_edges(["n00001", "n00002"], READER) == []
    assert client.sql_sent  # it looked
    assert len(client.gremlin_sent) == 2


@pytest.mark.parametrize("kind", ["nodes", "edges"])
async def test_an_absent_id_and_a_hidden_id_make_the_same_requests(kind: str) -> None:
    """The stand-in answers a hidden id's Gremlin read with nothing, as the access step does; an
    absent id has no record at all. The requests each sends must match in number and kind."""

    class Hiding(_Client):
        async def gremlin(self, query: str, **kw: Any) -> list[dict[str, Any]]:
            await super().gremlin(query, **kw)
            return []

    async def run(client: _Client) -> None:
        adapter, _ = _adapter(client)
        if kind == "nodes":
            await adapter.get_nodes(["n00007"], READER)
        else:
            await adapter.get_edges(["n00007"], READER)

    hidden, absent = Hiding(known=lambda _id: True), _Client(known=lambda _id: False)
    await run(hidden)
    await run(absent)
    assert hidden.schema_sent == absent.schema_sent
    assert len(hidden.sql_sent) == len(absent.sql_sent)
    assert [c for c, _ in hidden.sql_sent] == [c for c, _ in absent.sql_sent]
    assert len(hidden.gremlin_sent) == len(absent.gremlin_sent) == 1
    for sent in (hidden.gremlin_sent[0], absent.gremlin_sent[0]):
        assert sent.startswith("g.V(" if kind == "nodes" else "g.E(")
    assert "limit(0)" not in hidden.gremlin_sent[0] and "limit(0)" in absent.gremlin_sent[0]


def test_the_record_id_lookup_names_one_type_and_binds_the_ids() -> None:
    assert render_record_id_lookup_sql("mx_Person") == (
        "SELECT @rid AS rid FROM `mx_Person` WHERE id IN :ids"
    )
    with pytest.raises(ValueError):
        render_record_id_lookup_sql("mx_Person; DROP TYPE mx_Person")


# --- merging and ordering ----------------------------------------------------------------------


async def test_rows_come_back_ascending_by_id_across_chunks_whatever_order_the_store_gave() -> None:
    """The stand-in answers each chunk in descending order, so a result that is the rows as they
    came, chunk after chunk, is not ascending."""
    ids = [f"n{i:05d}" for i in range(1100)]
    adapter, _ = _adapter()
    nodes = await adapter.get_nodes(list(reversed(ids)), READER)
    assert [n.id for n in nodes] == ids
    edges = await adapter.get_edges(list(reversed(ids)), READER)
    assert [e.id for e in edges] == ids


async def test_an_id_the_store_holds_twice_comes_back_once() -> None:
    """Two stored copies of one id (ADR-056 Amendments 15 and 19): the stand-in sends every row
    twice, and one id asked at the start and the end of 1,101 is one result."""
    ids = [f"n{i:05d}" for i in range(1100)]
    adapter, _ = _adapter()
    nodes = await adapter.get_nodes([ids[0], *ids[1:], ids[0]], READER)
    assert [n.id for n in nodes] == ids
    edges = await adapter.get_edges([ids[0], *ids[1:], ids[0]], READER)
    assert [e.id for e in edges] == ids
