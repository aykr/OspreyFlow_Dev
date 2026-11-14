"""`search_nodes` without a store (ADR-124 Amendment 21): what it sends, and what it keeps.

Measured on 14 November 2026 on stack d (B's load, 642,460 nodes; `process/lanes/platform/
v052-measure/profile_m9.py`, under the rules lane's lease): the query as built,
`g.V().or(__.has(f, v), …)`, read every vertex in the store for each search, 5.4 to 5.7 s whatever
its limit, so M9's fallback (OpenSearch stopped) was over its 5 s figure. Now the candidates come
first, one SQL lookup per stored vertex type and field that type can hold, the value bound; the
match (`match_any_field`'s `or()`, with its gazetteer guard) and the access step are applied in a
traversal from those records alone.

What ArcadeDB answers for a hidden node, a gazetteer place, or each of step 4's queries as every
reader is proven against the store (`tests/conformance/graph_port/`, the gazetteer live files, and
the side-by-side run on stack d in `process/lanes/rules/adr124-am21/`). Here, the shape: nothing
starts from every vertex, a field is asked of every type that holds it, a request reader's lookups
leave out the gazetteer-only identifiers, a value nobody holds still sends its query, and
candidates past a chunk are all sent and the answer cut at the limit without repeats.
"""

from __future__ import annotations

import re
from typing import Any, cast

from adapters.graph_arcadedb.adapter import _ID_CHUNK, GraphArcadeDBAdapter
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal
from schemas.mapconfig import GAZETTEER_ONLY_IDENTIFIERS

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["case-a"])
CONDUIT = READER.model_copy(update={"datasets": None})
_NOW = "2026-01-01T00:00:00+00:00"
_TYPES_SQL = "SELECT name, type, indexes FROM schema:types"
_FIELD_SQL = re.compile(r"SELECT @rid AS rid FROM `([^`]+)` WHERE `([^`]+)` = :value")


def _node(rid: str) -> dict[str, Any]:
    return {
        "id": f"node-{rid.split(':')[1]}",
        "label": "mx_Person",
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
    """Stands in for ArcadeDB. `stored` are the vertex types it holds, each with its unique `id`
    index; `holders` maps (type, field) to the record ids whose field equals the value searched.
    A Gremlin query starting `g.V([...])` is answered with each named record, unmatched and
    unfiltered: the live suites prove the match and the access step. It keeps what it was sent."""

    def __init__(self, stored: list[str], holders: dict[tuple[str, str], list[str]]) -> None:
        self.stored = stored
        self.holders = holders
        self.sql_sent: list[tuple[str, str, dict[str, Any], str]] = []
        self.gremlin_sent: list[str] = []

    async def sql(self, command: str, *, params: Any = None, **_: Any) -> list[dict[str, Any]]:
        if command == _TYPES_SQL:
            return [
                {
                    "name": name,
                    "type": "vertex",
                    "indexes": [
                        {
                            "name": f"{name}[id]",
                            "typeName": name,
                            "unique": True,
                            "properties": ["id"],
                        }
                    ],
                }  # fmt: skip
                for name in self.stored
            ]
        found = _FIELD_SQL.fullmatch(command)
        assert found, command
        type_name, field_name = found.groups()
        self.sql_sent.append((type_name, field_name, dict(params or {}), command))
        return [{"rid": rid} for rid in self.holders.get((type_name, field_name), [])]

    async def gremlin(self, query: str, **_: Any) -> list[dict[str, Any]]:
        self.gremlin_sent.append(query)
        head = re.match(r"g\.V\(\[([^\]]*)\]\)", query)
        rids = re.findall(r"'(#\d+:\d+)'", head.group(1)) if head else []
        limit = int(re.search(r"\.limit\((\d+)\)\.elementMap\(\)$", query).group(1))  # type: ignore[union-attr]
        return [_node(rid) for rid in rids][:limit]


def _adapter(store: _Store) -> GraphArcadeDBAdapter:
    adapter = GraphArcadeDBAdapter(cast(Any, store), load_uk_le_scheme())
    adapter.use_schema(load_deployment_ontology())
    return adapter


def _every_type() -> list[str]:
    return [physical_type_name(e.name) for e in load_deployment_ontology().entity_types]


PERSON, ACCOUNT, LOCATION = (physical_type_name(t) for t in ("Person", "Account", "Location"))


async def test_no_search_starts_from_every_vertex() -> None:
    """The cause of M9's 5.4 s: `g.V().or(...)` reads the whole store. Each query now starts from
    its candidates' records, or matches nothing at once (`g.V().limit(0)`)."""
    store = _Store(_every_type(), {(PERSON, "family_name"): ["#9:1", "#9:2"]})
    found = await _adapter(store).search_nodes("Morlow", READER)
    assert [n.id for n in found] == ["node-1", "node-2"]
    assert store.gremlin_sent and all(
        q.startswith("g.V(['#") or q.startswith("g.V().limit(0).") for q in store.gremlin_sent
    ), store.gremlin_sent
    assert not any(q.startswith("g.V().or(") for q in store.gremlin_sent)


async def test_the_match_and_the_access_step_are_in_the_traversal_from_the_candidates() -> None:
    """Rule 3: the SQL lookup only says where the traversal starts. The match, with the gazetteer
    guard for a request reader, and the access step are applied there to every candidate."""
    store = _Store(_every_type(), {(PERSON, "family_name"): ["#9:1"]})
    adapter = _adapter(store)
    await adapter.search_nodes("Morlow", READER)
    (query,) = store.gremlin_sent
    assert "__.has('family_name','Morlow')" in query and "__.has('name','Morlow')" in query
    assert "TextP.startingWith('gazetteer-')" in query
    assert adapter._access.gremlin_has_step(READER) in query


async def test_a_field_is_asked_of_each_type_that_keeps_it_flattened_and_the_value_is_bound() -> (
    None
):
    """`g.V().or(__.has(f, v), …)` matched a field where a vertex keeps it at its top level: its
    type's identifiers and indexed properties, which the write flattens (`_indexed_property_names`).
    Any other property stays inside `properties`, where `has` never matched it: an `Account`'s
    unindexed `name` (stack d, 14 November 2026). So each type is asked those fields alone, and
    the value is never part of the text."""
    store = _Store(_every_type(), {})
    await _adapter(store).search_nodes("Copperleaf Imports", READER)
    asked = {(t, f) for t, f, _p, _c in store.sql_sent}
    assert {(LOCATION, "name"), (PERSON, "family_name"), (PERSON, "nino")} <= asked
    assert (ACCOUNT, "name") not in asked and (ACCOUNT, "account_number") in asked
    assert (PERSON, "name") not in asked
    assert all(p == {"value": "Copperleaf Imports"} for _t, _f, p, _c in store.sql_sent)
    assert not any("Copperleaf" in c for _t, _f, _p, c in store.sql_sent)


async def test_a_request_reader_looks_up_no_gazetteer_only_identifier() -> None:
    """ADR-147 Amendment 3: for a request reader no node is matched on an identifier only a
    gazetteer carries, so none is looked up; the Conduit's own work still asks them."""
    for principal, expect in ((READER, False), (CONDUIT, True)):
        store = _Store(_every_type(), {})
        await _adapter(store).search_nodes("node/1", principal)
        fields = {f for _t, f, _p, _c in store.sql_sent}
        assert bool(fields & set(GAZETTEER_ONLY_IDENTIFIERS)) is expect, (principal, fields)
        assert "uprn" in fields  # a case's own identifier is asked of both


async def test_a_type_the_store_does_not_hold_is_not_asked() -> None:
    store = _Store([PERSON], {})
    await _adapter(store).search_nodes("Morlow", READER)
    assert {t for t, _f, _p, _c in store.sql_sent} == {PERSON}


async def test_a_value_nobody_holds_still_sends_its_query() -> None:
    """Rule 3: a value no vertex holds costs the round trip a value only hidden vertices hold."""
    nobody = _Store(_every_type(), {})
    hidden = _Store(_every_type(), {(PERSON, "family_name"): ["#9:7"]})
    assert await _adapter(nobody).search_nodes("Zzz", READER) == []
    await _adapter(hidden).search_nodes("Zzz", READER)
    assert len(nobody.gremlin_sent) == len(hidden.gremlin_sent) == 1
    assert nobody.gremlin_sent[0].startswith("g.V().limit(0).")
    assert len(nobody.sql_sent) == len(hidden.sql_sent)


async def test_candidates_past_a_chunk_are_all_sent_and_the_answer_cut_at_the_limit() -> None:
    """Rule 2: every chunk's candidates are traversed (so the one-past row that says `more` is
    there whatever chunk it is in), the answer holds no node twice, and it stops at the limit.
    A candidate found by two fields is traversed once."""
    many = [f"#9:{i}" for i in range(2 * _ID_CHUNK + 500)]
    store = _Store(
        _every_type(),
        {(PERSON, "family_name"): many, (PERSON, "given_names"): many[:10]},
    )
    found = await _adapter(store).search_nodes("Smith", READER, limit=101)
    assert len(store.gremlin_sent) == 3
    starts = [re.findall(r"'(#\d+:\d+)'", q.split(")", 1)[0]) for q in store.gremlin_sent]
    assert sorted(r for chunk in starts for r in chunk) == sorted(many)
    assert len(found) == 101 and len({n.id for n in found}) == 101


async def test_an_empty_field_set_sends_nothing() -> None:
    store = _Store(_every_type(), {})
    adapter = GraphArcadeDBAdapter(cast(Any, store), load_uk_le_scheme())
    adapter.use_schema(load_deployment_ontology().model_copy(update={"entity_types": []}))
    assert await adapter.search_nodes("x", READER) == []
    assert store.sql_sent == [] and store.gremlin_sent == []
