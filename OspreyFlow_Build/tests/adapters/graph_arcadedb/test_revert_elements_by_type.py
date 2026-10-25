"""ADR-127 Amendment 6 (B2-4c): the revert and the revert's lookups go by each type's unique `id`
index, never by a scan, and know which kind they were asked about.

Gremlin's `has("id", within(...))` scans the store, and `g.E()` matches a link of any type, so the
revert first resolves each id to its stored type through that type's unique index and then sets
`reverted` by SQL on that type, in chunks. The store here is a stand-in that refuses what the real
one would: it answers no Gremlin scan of ids (it raises), only the statements the adapter is meant
to send. What a mistake would do, and the case that catches it:

- an id scanned for rather than looked up (`test_a_revert_sends_sql_by_type_and_no_gremlin_scan`);
- a node id that is also a link's id reverting the link too, or the reverse
  (`test_a_node_id_is_looked_up_among_node_types_only_and_a_link_id_among_link_types_only`);
- an id two types hold reverted on both, or on one chosen by chance, and the rest of the call
  already written (`test_an_id_two_types_hold_is_refused_before_anything_is_written`);
- thousands of ids in one statement (`test_ids_go_in_chunks_of_the_adapters_size`);
- a lookup of the load a node was last written by, or of the live links at a node, that is filtered
  by what a reader may read (they answer whatever the caller may read, as the port says)."""

from __future__ import annotations

import re
from typing import Any

import pytest

from adapters.graph_arcadedb import adapter as adapter_module
from adapters.graph_arcadedb.adapter import _ID_CHUNK
from ontology.handling import load_uk_le_scheme
from ports.graph import AmbiguousElementId, StoredNode

_IDS = re.compile(r"SELECT id FROM `(\w+)` WHERE id IN :ids")
_RID = re.compile(r"SELECT @rid AS rid FROM `(\w+)` WHERE id IN :ids")
_UPDATE = re.compile(r"UPDATE `(\w+)` SET reverted = true WHERE id IN :ids")
_LOADS = re.compile(
    r"SELECT id, audit\.load_id AS load_id, reverted FROM `(\w+)` WHERE id IN :ids"
)
_GEOMETRY = re.compile(
    r"SELECT id, properties\.geometry_ref AS ref FROM `(\w+)` "
    r"WHERE properties\.geometry_ref IN :refs "
    r"AND \(reverted = false OR reverted IS NULL\) AND superseded_by IS NULL"
)


class TypedStore:
    """Vertex types and edge types, each with rows by id. `reverted` flags are set only by the
    statement that names a type; a Gremlin scan of ids raises."""

    def __init__(self) -> None:
        self.vertices: dict[str, dict[str, dict[str, Any]]] = {"Person": {}, "Document": {}}
        self.edges: dict[str, dict[str, dict[str, Any]]] = {"ASSOCIATE_OF": {}, "FAMILY_OF": {}}
        self.sql_sent: list[str] = []
        self.gremlin_sent: list[str] = []
        self.update_sizes: list[tuple[str, int]] = []
        self._rids: dict[str, str] = {}

    def vertex(self, type_name: str, node_id: str, **fields: Any) -> None:
        self.vertices[type_name][node_id] = {"id": node_id, **fields}

    def edge(self, type_name: str, edge_id: str, source: str, target: str, **fields: Any) -> None:
        self.edges[type_name][edge_id] = {
            "id": edge_id,
            "source": source,
            "target": target,
            **fields,
        }

    def _rid(self, node_id: str) -> str:
        return self._rids.setdefault(node_id, f"#{len(self._rids) + 1}:0")

    def _table(self, type_name: str) -> dict[str, dict[str, Any]]:
        return self.vertices[type_name] if type_name in self.vertices else self.edges[type_name]

    async def begin_transaction(self) -> str:
        return "tx"

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        self.sql_sent.append(command)
        if command.startswith("SELECT name, type, indexes FROM schema:types"):
            index = [{"unique": True, "properties": ["id"]}]
            return [
                *({"name": n, "type": "vertex", "indexes": index} for n in self.vertices),
                *({"name": n, "type": "edge", "indexes": index} for n in self.edges),
            ]
        assert params is not None
        if (m := _IDS.fullmatch(command)) is not None:
            table = self._table(m.group(1))
            return [{"id": i} for i in params["ids"] if i in table]
        if (m := _RID.fullmatch(command)) is not None:
            table = self._table(m.group(1))
            return [{"rid": self._rid(i)} for i in params["ids"] if i in table]
        if (m := _UPDATE.fullmatch(command)) is not None:
            table = self._table(m.group(1))
            self.update_sizes.append((m.group(1), len(params["ids"])))
            for i in params["ids"]:
                if i in table:
                    table[i]["reverted"] = True
            return []
        if (m := _LOADS.fullmatch(command)) is not None:
            table = self._table(m.group(1))
            return [
                {"id": i, "load_id": table[i].get("load_id"), "reverted": table[i].get("reverted")}
                for i in params["ids"]
                if i in table
            ]
        if (m := _GEOMETRY.fullmatch(command)) is not None:
            table = self._table(m.group(1))
            return [
                {"id": r["id"], "ref": r["ref"]}
                for r in table.values()
                if r.get("ref") in params["refs"]
                and not r.get("reverted")
                and not r.get("superseded_by")
            ]
        raise AssertionError(f"unexpected SQL: {command}")

    async def gremlin(
        self, query: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[Any]:
        self.gremlin_sent.append(query)
        if 'has("id"' in query and "within(" in query:
            raise AssertionError(f"a scan of ids by Gremlin: {query}")
        if query.startswith("g.V([") and ".bothE()" in query:
            asked = {i for i, rid in self._rids.items() if rid in re.findall(r"#\d+:\d+", query)}
            found = [
                {"result": e["id"]}
                for table in self.edges.values()
                for e in table.values()
                if (e["source"] in asked or e["target"] in asked)
                # As the store: a reverted or superseded link is left out only if the query says so.
                and not ('has("reverted",false)' in query and e.get("reverted"))
                and not ('hasNot("superseded_by")' in query and e.get("superseded_by"))
            ]
            return found
        raise AssertionError(f"unexpected query: {query}")


def _adapter(store: TypedStore) -> adapter_module.GraphArcadeDBAdapter:
    return adapter_module.GraphArcadeDBAdapter(store, load_uk_le_scheme())  # type: ignore[arg-type]


async def test_a_revert_sends_sql_by_type_and_no_gremlin_scan() -> None:
    store = TypedStore()
    store.vertex("Person", "p1")
    store.vertex("Document", "d1")
    store.vertex("Person", "keep")
    store.edge("ASSOCIATE_OF", "e1", "p1", "keep")
    store.edge("ASSOCIATE_OF", "e-keep", "p1", "keep")
    graph = _adapter(store)
    await graph.revert_elements(["p1", "d1"], ["e1"], "tx")
    assert store.vertices["Person"]["p1"]["reverted"] is True
    assert store.vertices["Document"]["d1"]["reverted"] is True
    assert store.edges["ASSOCIATE_OF"]["e1"]["reverted"] is True
    assert "reverted" not in store.vertices["Person"]["keep"]
    assert "reverted" not in store.edges["ASSOCIATE_OF"]["e-keep"]
    assert store.gremlin_sent == [], "every id went by the unique index and SQL"
    assert {t for t, _ in store.update_sizes} == {"Person", "Document", "ASSOCIATE_OF"}, (
        "an update names only the type that holds the ids"
    )


async def test_a_node_id_is_looked_up_among_node_types_only_and_a_link_id_among_link_types_only() -> (
    None
):
    store = TypedStore()
    store.vertex("Person", "x")
    store.edge("ASSOCIATE_OF", "x", "x", "x")  # the same string, a link's id
    graph = _adapter(store)
    await graph.revert_elements(["x"], [], "tx")
    assert store.vertices["Person"]["x"]["reverted"] is True
    assert "reverted" not in store.edges["ASSOCIATE_OF"]["x"]
    store.vertices["Person"]["x"].pop("reverted")
    await graph.revert_elements([], ["x"], "tx")
    assert store.edges["ASSOCIATE_OF"]["x"]["reverted"] is True
    assert "reverted" not in store.vertices["Person"]["x"]
    asked = [c for c in store.sql_sent if c.startswith("SELECT id FROM")]
    assert asked, "the lookups were sent"


async def test_an_id_two_types_hold_is_refused_before_anything_is_written() -> None:
    store = TypedStore()
    store.vertex("Person", "ok")
    store.vertex("Person", "twice")
    store.vertex("Document", "twice")
    graph = _adapter(store)
    with pytest.raises(AmbiguousElementId) as raised:
        await graph.revert_elements(["ok", "twice"], [], "tx")
    assert raised.value.kind == "node" and raised.value.count == 1
    assert "twice" not in str(raised.value), "the refusal names a count, not an id"
    assert store.update_sizes == [] and "reverted" not in store.vertices["Person"]["ok"]


async def test_ids_go_in_chunks_of_the_adapters_size() -> None:
    store = TypedStore()
    ids = [f"p{i}" for i in range(_ID_CHUNK + 40)]
    for i in ids:
        store.vertex("Person", i)
    graph = _adapter(store)
    await graph.revert_elements([*ids, ids[0]], [], "tx")
    assert [n for t, n in store.update_sizes if t == "Person"] == [_ID_CHUNK, 40]
    assert all(r.get("reverted") for r in store.vertices["Person"].values())


async def test_live_edges_touching_resolves_record_ids_by_index_and_reads_live_links_only() -> None:
    store = TypedStore()
    for node in ("a", "b", "c"):
        store.vertex("Person", node)
    store.edge("ASSOCIATE_OF", "ab", "a", "b")
    store.edge("ASSOCIATE_OF", "bc-reverted", "b", "c", reverted=True)
    store.edge("FAMILY_OF", "bc-superseded", "b", "c", superseded_by="x")
    store.edge("FAMILY_OF", "ac", "a", "c")
    graph = _adapter(store)
    assert await graph.live_edges_touching(["a"]) == {"ab", "ac"}
    assert await graph.live_edges_touching(["b"]) == {"ab"}
    assert await graph.live_edges_touching(["nobody"]) == set()
    assert any(c.startswith("SELECT @rid AS rid") for c in store.sql_sent)
    assert not any('has("id"' in q for q in store.gremlin_sent)


async def test_live_edges_touching_sends_one_lookup_per_chunk() -> None:
    store = TypedStore()
    ids = [f"p{i}" for i in range(_ID_CHUNK + 5)]
    for i in ids:
        store.vertex("Person", i)
    store.edge("ASSOCIATE_OF", "e", ids[-1], ids[0])
    graph = _adapter(store)
    assert await graph.live_edges_touching(ids) == {"e"}
    assert len([q for q in store.gremlin_sent if q.startswith("g.V([")]) == 2


async def test_stored_writes_reads_audit_and_the_flag_by_the_index_whatever_the_state() -> None:
    store = TypedStore()
    store.vertex("Person", "n1", load_id="load-1")
    store.vertex("Person", "n2", load_id=None, reverted=True)
    store.vertex("Document", "d1", load_id="load-2", superseded_by="d2")
    graph = _adapter(store)
    found = await graph.stored_writes(["n1", "n2", "d1", "absent"])
    assert found == {
        "n1": StoredNode(load_id="load-1", reverted=False),
        "n2": StoredNode(load_id=None, reverted=True),
        "d1": StoredNode(load_id="load-2", reverted=False),
    }
    assert await graph.stored_writes([]) == {}
    assert store.gremlin_sent == []


async def test_live_nodes_naming_geometry_leaves_out_reverted_and_superseded_nodes() -> None:
    store = TypedStore()
    store.vertex("Person", "l1", ref="g-1")
    store.vertex("Person", "l2", ref="g-1")
    store.vertex("Document", "l3", ref="g-2", reverted=True)
    store.vertex("Document", "l4", ref="g-3", superseded_by="x")
    graph = _adapter(store)
    assert await graph.live_nodes_naming_geometry(["g-1", "g-2", "g-3", "g-4"]) == {
        "g-1": {"l1", "l2"}
    }
    assert await graph.live_nodes_naming_geometry([]) == {}


@pytest.mark.parametrize(
    "name", ["live_edges_touching", "live_nodes_naming_geometry", "stored_writes"]
)
async def test_a_bare_string_is_refused_not_read_as_a_list_of_characters(name: str) -> None:
    graph = _adapter(TypedStore())
    with pytest.raises(TypeError):
        await getattr(graph, name)("abc")
