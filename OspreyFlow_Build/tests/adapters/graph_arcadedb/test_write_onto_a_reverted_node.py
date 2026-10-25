"""ADR-127 Amendment 6 (the revert, B2-4c): a write onto a reverted node is a fresh create.

A reverted node keeps its id for good (it is never deleted), so a load run again after its revert
writes the same ids, and a content Document's id is fixed by its content (`content:<sha>`). Before
this, `upsert_nodes` found the reverted node and merged into it: the rerun's Document took the
reverted node's marking and datasets (a higher classification survived the revert, so a reader
cleared for the rerun could not read it), and the load recorded it as merged. Now:

- `upsert_nodes` clears `reverted` and takes the write's body whole, as for a node never stored;
- `existing_node_ids` leaves a reverted node out, so the load records it as created.

The store is a stand-in that refuses what the real one refuses (a duplicate `id` on insert) and
answers the id lookup honestly: a reverted row is left out only if the statement says so, so a
lookup that forgot the filter would still report it."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from adapters.graph_arcadedb import adapter as adapter_module
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

NODE_TYPE = "Person"
NOW = datetime(2026, 10, 25, tzinfo=UTC)
_IDS = re.compile(
    r"SELECT id FROM `(\w+)` WHERE id IN :ids"
    r"( AND \(reverted = false OR reverted IS NULL OR superseded_by IS NOT NULL\))?"
)
_REVERT = re.compile(r"UPDATE `(\w+)` SET reverted = true WHERE id IN :ids")


class NodeStore:
    """The part of ArcadeDB the node write and the id lookup touch."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.sql_sent: list[str] = []

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        self.sql_sent.append(command)
        if command.startswith("SELECT name, type, indexes FROM schema:types"):
            return [
                {
                    "name": physical_type_name(NODE_TYPE),
                    "type": "vertex",
                    "indexes": [{"unique": True, "properties": ["id"]}],
                }
            ]
        assert params is not None
        found = _IDS.fullmatch(command)
        if found is not None:
            filtered = found.group(2) is not None
            return [
                {"id": i}
                for i in params["ids"]
                if i in self.rows
                and not (
                    filtered
                    and self.rows[i].get("reverted")
                    and not self.rows[i].get("superseded_by")
                )
            ]
        if _REVERT.fullmatch(command) is not None:
            for i in params["ids"]:
                if i in self.rows:
                    self.rows[i]["reverted"] = True
            return []
        if command.startswith("INSERT INTO "):
            if params["id"] in self.rows:
                raise AssertionError(f"duplicate id {params['id']!r}: the unique index refuses")
            self.rows[params["id"]] = dict(params)
            return []
        if command.startswith("UPDATE ") and command.endswith(" WHERE id = :id"):
            # As an `UPDATE ... SET` does: the properties named are set, any other is left as it was.
            self.rows[params["id"]].update(params)
            return []
        raise AssertionError(f"unexpected SQL: {command}")

    async def gremlin(
        self, query: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[Any]:
        if ".elementMap()" in query:
            node_id = query.split("'")[1] if "'" in query else query.split('"')[1]
            return [self.rows[node_id]] if node_id in self.rows else []
        raise AssertionError(f"unexpected query: {query}")


def _adapter(store: NodeStore) -> adapter_module.GraphArcadeDBAdapter:
    graph = adapter_module.GraphArcadeDBAdapter(store, load_uk_le_scheme())  # type: ignore[arg-type]
    graph._schema = load_default_ontology()
    return graph


def _write(
    node_id: str, *, classification: str, load_id: str, datasets: list[str], source: str
) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type=NODE_TYPE,
        properties={"family_name": f"from {source}"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id=source, locator="row 1", excerpt_hash="")],
            first_seen=NOW,
        ),
        handling=Handling(
            classification=classification, handling_code="P", originator="u", owning_unit="u"
        ),
        created_by="loader",
        created_at=NOW,
        load_id=load_id,
        datasets=datasets,
    )


async def _revert(graph: adapter_module.GraphArcadeDBAdapter, node_id: str) -> None:
    tx = await graph.begin_transaction()
    await graph.revert_elements([node_id], [], tx)
    await graph.commit_transaction(tx)


async def test_a_write_onto_a_reverted_node_takes_the_new_body_whole() -> None:
    store = NodeStore()
    graph = _adapter(store)
    first = _write("n1", classification="SECRET", load_id="load-1", datasets=["a"], source="one")
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([first], tx)
    await graph.commit_transaction(tx)
    await _revert(graph, "n1")
    assert store.rows["n1"]["reverted"] is True

    again = _write("n1", classification="OFFICIAL", load_id="load-2", datasets=["b"], source="two")
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([again], tx)
    await graph.commit_transaction(tx)

    row = store.rows["n1"]
    assert row["reverted"] is False, "the node is live again"
    assert row["handling_classification"] == "OFFICIAL", "not raised by the reverted body"
    assert row["datasets"] == ["b"], "not the union with the reverted node's datasets"
    assert row["properties"] == {"family_name": "from two"}
    assert [s["document_id"] for s in row["provenance"]["sources"]] == ["two"]
    assert (row["audit"]["load_id"], row["audit"]["revision"]) == ("load-2", 1)
    assert row["audit"]["reverted"] is False


async def test_a_write_onto_a_live_node_still_merges() -> None:
    """The change is for a reverted node only: a live one keeps the merge (ADR-102)."""
    store = NodeStore()
    graph = _adapter(store)
    first = _write("n1", classification="OFFICIAL", load_id="load-1", datasets=["a"], source="one")
    second = _write("n1", classification="SECRET", load_id="load-2", datasets=["b"], source="two")
    for write in (first, second):
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([write], tx)
        await graph.commit_transaction(tx)
    row = store.rows["n1"]
    assert row["handling_classification"] == "SECRET"
    assert row["datasets"] == ["a", "b"]
    assert row["audit"]["revision"] == 2
    assert [s["document_id"] for s in row["provenance"]["sources"]] == ["one", "two"]


async def test_existing_node_ids_leaves_out_a_reverted_node() -> None:
    store = NodeStore()
    graph = _adapter(store)
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            _write(i, classification="OFFICIAL", load_id="load-1", datasets=["a"], source="one")
            for i in ("n1", "n2")
        ],
        tx,
    )
    await graph.commit_transaction(tx)
    assert await graph.existing_node_ids(["n1", "n2", "n3"]) == {"n1", "n2"}
    await _revert(graph, "n1")
    assert await graph.existing_node_ids(["n1", "n2", "n3"]) == {"n2"}
    # Written again, it exists again, and as one node (the unique id was never violated).
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [_write("n1", classification="OFFICIAL", load_id="load-2", datasets=["a"], source="two")],
        tx,
    )
    await graph.commit_transaction(tx)
    assert await graph.existing_node_ids(["n1"]) == {"n1"}


async def test_a_node_reverted_and_superseded_stays_superseded_when_written_again() -> None:
    """A write onto a reverted node clears `reverted` and nothing else (ADR-127 Amendment 6). A node
    that is also superseded stays superseded, so reads keep following its successor and there are
    never two live revisions; the fresh body is stored, and `superseded_by` is left as it was, on
    the node and in its audit."""
    store = NodeStore()
    graph = _adapter(store)
    first = _write("n1", classification="OFFICIAL", load_id="load-1", datasets=["a"], source="one")
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([first], tx)
    await graph.commit_transaction(tx)
    store.rows["n1"]["superseded_by"] = "n1-revision-2"  # as `supersede_node` leaves it
    store.rows["n1"]["audit"]["superseded_by"] = "n1-revision-2"
    await _revert(graph, "n1")

    again = _write("n1", classification="OFFICIAL", load_id="load-2", datasets=["a"], source="two")
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([again], tx)
    await graph.commit_transaction(tx)
    row = store.rows["n1"]
    assert row["superseded_by"] == "n1-revision-2", "still the old revision"
    assert row["audit"]["superseded_by"] == "n1-revision-2"
    assert row["reverted"] is False
    assert row["properties"] == {"family_name": "from two"}
    assert not [c for c in store.sql_sent if "REMOVE" in c], "nothing is removed from the node"


async def test_existing_node_ids_names_a_node_reverted_and_superseded() -> None:
    """A write onto it merges (it stays superseded), so a load writing it records it as merged and
    its own revert refuses rather than taking it back."""
    store = NodeStore()
    graph = _adapter(store)
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            _write(i, classification="OFFICIAL", load_id="load-1", datasets=["a"], source="one")
            for i in ("plain", "both")
        ],
        tx,
    )
    await graph.commit_transaction(tx)
    store.rows["both"]["superseded_by"] = "both-2"
    await _revert(graph, "plain")
    await _revert(graph, "both")
    assert await graph.existing_node_ids(["plain", "both"]) == {"both"}
