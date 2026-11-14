"""`edges_among` without a store (ADR-124 Amendment 20): what it sends, and what it keeps of what
comes back.

Measured on 14 November 2026 (`process/lanes/rules-b/v052batch-50k/findings.md`, stack b): the
query as it was built put every id into the Groovy script as a literal list, twice. Its plan read
every vertex in the store, and somewhere between 10,000 and 25,000 ids ArcadeDB stopped being able
to compile it ("Class too large"). So a batch past that size failed, and so did `open_view` on a
view that large. Now each chunk of ids is resolved to record ids through each vertex type's unique
`id` index, a traversal starts from those records, and a link is kept only where its far end is one
of the ids asked for.

What the adapter returns for a hidden link, a hidden far end or a set past the old wall is proven
against ArcadeDB (`tests/conformance/graph_port/test_edges_among_at_scale.py`). Here, the shape: a
query's text grows with its chunk and not with the set, nothing scans the store, the far end is
tested, a link across chunks is found once, and an absent id costs what a hidden one costs.
"""

from __future__ import annotations

import re
from typing import Any, cast

from adapters.graph_arcadedb.adapter import _ID_CHUNK, GraphArcadeDBAdapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

from .edge_store import refuse_scans

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"])
_NOW = "2026-01-01T00:00:00+00:00"
_TYPES_SQL = "SELECT name, type, indexes FROM schema:types"


def _ids(count: int) -> list[str]:
    return [f"n{i:06d}" for i in range(count)]


def _rid(identifier: str) -> str:
    return f"#9:{int(identifier[1:])}"


def _id_of(rid: str) -> str:
    return f"n{int(rid.split(':')[1]):06d}"


def _link(link_id: str, source: str, target: str) -> dict[str, Any]:
    return {
        "id": link_id,
        "label": "mx_ASSOCIATE_OF",
        "source": source,
        "target": target,
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


class _Store:
    """Stands in for ArcadeDB. `nodes` are the ids it holds (SQL resolves each to a record id),
    `links` its links as (id, source, target). A Gremlin query starting `g.V([...])` is answered
    with each named record's outgoing links, one row each, as `{'e': <the link>, 't': <its far end's
    id>}`, which is the shape the adapter asks for. Nothing here applies an access step: the live
    suite proves that. It keeps what it was sent."""

    def __init__(self, nodes: list[str], links: list[tuple[str, str, str]]) -> None:
        self.nodes = set(nodes)
        self.out: dict[str, list[tuple[str, str, str]]] = {}
        for link in links:
            self.out.setdefault(link[1], []).append(link)
        self.sql_sent: list[tuple[str, dict[str, Any]]] = []
        self.gremlin_sent: list[str] = []

    async def sql(self, command: str, *, params: Any = None, **_: Any) -> list[dict[str, Any]]:
        if command == _TYPES_SQL:
            ontology = load_default_ontology()
            index = {"name": "T[id]", "typeName": "T", "unique": True, "properties": ["id"]}
            # One vertex type holds every id, as the store holds each node once.
            return [{"name": f"mx_{ontology.entity_types[0].name}", "type": "vertex",
                     "indexes": [index]}]  # fmt: skip
        self.sql_sent.append((command, dict(params or {})))
        return [{"rid": _rid(i)} for i in (params or {}).get("ids", []) if i in self.nodes]

    async def gremlin(self, query: str, **_: Any) -> list[dict[str, Any]]:
        self.gremlin_sent.append(query)
        head = re.match(r"g\.V\(\[([^\]]*)\]\)", query)
        starts = re.findall(r"'(#\d+:\d+)'", head.group(1)) if head else []
        return [{"e": _link(*link), "t": link[2]}
                for rid in starts for link in self.out.get(_id_of(rid), [])]  # fmt: skip


def _adapter(store: _Store) -> GraphArcadeDBAdapter:
    return GraphArcadeDBAdapter(cast(Any, store), load_uk_le_scheme())


async def test_a_query_s_text_grows_with_its_chunk_not_with_the_set() -> None:
    """The compile wall: 50,000 ids in one script did not compile. Each query now carries at most
    one chunk's record ids, so its length at 50,000 ids is about what it is at 2,000 (a record id
    there is one digit longer). Red on the query as it was built: one query of every id, twice, 25
    times as long."""

    async def longest(count: int) -> tuple[int, int]:
        store = _Store(_ids(count), [])
        await _adapter(store).edges_among(_ids(count), READER)
        return max(len(q) for q in store.gremlin_sent), len(store.gremlin_sent)

    small, large = await longest(2_000), await longest(50_000)
    assert large[1] == 50_000 // _ID_CHUNK
    assert large[0] < small[0] * 1.25, (small, large)  # a record id one digit longer, no more


async def test_no_query_looks_ids_up_by_scanning_the_store() -> None:
    """`has("id", within(...))` reads every vertex (the plan at 5,000 ids: 50,568 vertices read);
    the ids are resolved through the type's unique index by SQL, with the ids bound, never in the
    text."""
    ids = _ids(1_500)
    store = _Store(ids, [("l1", ids[0], ids[1])])
    await _adapter(store).edges_among(ids, READER)
    for query in store.gremlin_sent:
        refuse_scans(query)
        assert ids[0] not in query, "an id is in the text; only record ids belong there"
    assert store.sql_sent and all(p.get("ids") for _, p in store.sql_sent)


async def test_a_link_is_kept_only_where_its_far_end_was_asked_for() -> None:
    a, b, c, outside = _ids(4)
    store = _Store([a, b, c, outside], [("ab", a, b), ("bc", b, c), ("b-out", b, outside)])
    among = await _adapter(store).edges_among([a, b, c], READER)
    assert sorted(e.id for e in among) == ["ab", "bc"]


async def test_links_across_a_chunk_boundary_are_each_found_once() -> None:
    """Both directions across the boundary between the first and second chunks, a link inside each
    chunk, and a self-loop: each once. A link is reached only from its own source's chunk."""
    ids = _ids(_ID_CHUNK + 200)
    first, second = ids[5], ids[_ID_CHUNK + 5]
    links = [("forward", first, second), ("back", second, first), ("in-first", ids[0], ids[1]),
             ("in-second", ids[-1], ids[-2]), ("loop", ids[7], ids[7])]  # fmt: skip
    store = _Store(ids, links)
    among = await _adapter(store).edges_among(list(reversed(ids)), READER)
    assert sorted(e.id for e in among) == sorted(link[0] for link in links)
    assert len(store.gremlin_sent) == 2


async def test_an_absent_id_costs_what_a_hidden_one_costs() -> None:
    """Rule 3: a hidden id resolves to a record (its read then finds nothing through the access
    step); an absent one does not. The query is sent either way, so the number of round trips does
    not tell them apart, even for a chunk where nothing resolved at all."""
    ids = _ids(_ID_CHUNK + 1)
    held = _Store(ids, [])
    await _adapter(held).edges_among(ids, READER)
    absent = _Store(ids[:-1], [])
    await _adapter(absent).edges_among(ids, READER)
    assert len(absent.gremlin_sent) == len(held.gremlin_sent) == 2
    assert len(absent.sql_sent) == len(held.sql_sent)
    assert absent.gremlin_sent[-1].startswith("g.V().limit(0)")


async def test_the_link_types_narrow_every_chunk_s_query() -> None:
    ids = _ids(_ID_CHUNK + 1)
    store = _Store(ids, [])
    await _adapter(store).edges_among(ids, READER, edge_types=["FAMILY_OF"])
    assert len(store.gremlin_sent) == 2
    assert all("hasLabel(" in q and "FAMILY_OF" in q for q in store.gremlin_sent)


async def test_an_empty_or_one_node_set_sends_nothing() -> None:
    store = _Store(_ids(1), [])
    assert await _adapter(store).edges_among([], READER) == []
    assert await _adapter(store).edges_among(["n000000", "n000000"], READER) == []
    assert store.sql_sent == [] and store.gremlin_sent == []
