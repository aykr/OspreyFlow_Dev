"""A Join's provenance, written by the real Map write and read back through the real ArcadeDB
adapter (the orchestrator's settlement of 8 November 2026, Q2 (a): one `SourceRef` per input row in
the element's existing `provenance.sources`, a Join giving two, with no adapter change; and its
settlement of round 1: no row key, raw or hashed, in provenance).

The offline cases (`test_staged_run.py`) prove what the engine hands the graph; this proves the
store keeps it: an adapter that dropped `load_id`, or kept only the first source, would pass
offline and fail here. The writes go through the Conduit's own `DatasetStampingGraph`, so each
element is stamped with the loading case's dataset, and the access case reads it as a principal of
a case on another dataset (rule 4: every read path gets an access-control test).

Live: run under a lease (`stack_lease.sh acquire studio …`, the ports it prints pinned); the
staged Parquet goes to a temporary directory, so no object store is touched.
"""

from __future__ import annotations

from typing import Any

from services.api.dataset_scope import DatasetStampingGraph
from services.ingest.staged_run import run_staged_recipe
from services.ingest.staging import ObjectStorageConfig

from adapters.graph_arcadedb.testing import arcadedb_adapter
from schemas.domain import EdgeWrite, NodeWrite, Principal
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_staged_run import ONTOLOGY, RECIPE, SCHEME, inputs

#: The dataset the run loads into: the gate's (`dataset_id`) and the stamp's, one and the same, as
#: the reference list's own `dataset_id` is (review round 2).
DATASET = "pid"
SHARED = "pid_shared"
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1", datasets=[DATASET])
ELSEWHERE = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1", datasets=["ledger"])


class _TwoDatasetStamping:
    """The Conduit's `DatasetStampingGraph`, stamping two datasets instead of one: an element in two
    datasets is what ADR-130 Amendment 2 withholds sources of from a case reading one. Every call
    but the two writes goes to the adapter unchanged, as the Conduit's does."""

    def __init__(self, inner: Any, datasets: list[str]) -> None:
        self._inner, self._datasets = inner, datasets

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def upsert_nodes(self, nodes: Any, tx: Any) -> Any:
        stamped = [n.model_copy(update={"datasets": self._datasets}) for n in nodes]
        return await self._inner.upsert_nodes(stamped, tx)

    async def upsert_edges(self, edges: Any, tx: Any) -> Any:
        stamped = [e.model_copy(update={"datasets": self._datasets}) for e in edges]
        return await self._inner.upsert_edges(stamped, tx)


async def _load(
    graph: Any, written: list[NodeWrite | EdgeWrite], *, two_datasets: bool = False
) -> Any:
    sources, lists = inputs()
    loader = LOADER
    stamping: Any = DatasetStampingGraph(graph, dataset=DATASET)
    if two_datasets:
        loader = LOADER.model_copy(update={"datasets": [DATASET, SHARED]})
        stamping = _TwoDatasetStamping(graph, [DATASET, SHARED])
    tx = await stamping.begin_transaction()
    done = await run_staged_recipe(
        RECIPE,
        sources=sources,
        lists=lists,
        dataset_id=DATASET,
        graph=stamping,
        ontology=ONTOLOGY,
        tx=tx,
        principal=loader,
        load_id="ld-live-1",
        investigation_scope="case-live-1",
        storage=ObjectStorageConfig(bucket="staging"),
        scheme=SCHEME,
        written=written,
    )
    await stamping.commit_transaction(tx)
    return done


async def test_a_join_s_two_sides_and_its_list_row_are_stored_and_read_back() -> None:
    written: list[NodeWrite | EdgeWrite] = []
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        done = await _load(graph, written)
        assert done.report.edges_created > 0

        owner = await graph.find_node("Person", "family_name", "WHITLOW", LOADER)
        assert owner is not None
        [stored_owner] = await graph.get_nodes([owner.id], LOADER)
        stored = {(s.document_id, s.locator, s.load_id) for s in stored_owner.provenance.sources}
        assert ("visit_bookings", "row 0", "ld-vb-1") in stored
        assert ("number_owners", "row 0", "ld-no-1") in stored
        # The list row the establishment came from survives storage too (review round 1, item 11).
        assert ("reference_list:establishments@v3", "row 0", None) in stored
        assert '"row_key"' not in stored_owner.model_dump_json()

        uses_ids = [
            w.id
            for w in written
            if isinstance(w, EdgeWrite) and w.type == "USES" and w.source == owner.id
        ]
        assert uses_ids
        [link] = await graph.get_edges(uses_ids[:1], LOADER)
        sides = {(s.document_id, s.locator, s.load_id) for s in link.provenance.sources}
        assert {
            ("visit_bookings", "row 0", "ld-vb-1"),
            ("number_owners", "row 0", "ld-no-1"),
        } <= sides
        assert ("visit_bookings", "row 4", "ld-vb-1") in sides
        assert '"row_key"' not in link.model_dump_json()


async def test_a_reader_of_another_dataset_reads_no_staged_element_nor_its_sources() -> None:
    """Rule 4: the staged elements' new provenance is read only within the dataset that loaded
    them. A principal whose case reads another dataset finds no staged node or link by any of the
    reads this file uses; the loader, on the same store, finds them all."""
    written: list[NodeWrite | EdgeWrite] = []
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _load(graph, written)
        node_ids = [w.id for w in written if isinstance(w, NodeWrite)]
        edge_ids = [w.id for w in written if isinstance(w, EdgeWrite)]
        assert node_ids and edge_ids
        assert await graph.find_node("Person", "family_name", "WHITLOW", ELSEWHERE) is None
        assert await graph.get_nodes(node_ids, ELSEWHERE) == []
        assert await graph.get_edges(edge_ids, ELSEWHERE) == []
        # The comparison never holds over nothing: the loader reads every one of them.
        assert len(await graph.get_nodes(node_ids, LOADER)) == len(set(node_ids))
        assert len(await graph.get_edges(edge_ids, LOADER)) > 0


async def test_a_case_reading_one_of_an_element_s_two_datasets_is_sent_none_of_its_sources() -> (
    None
):
    """Rule 4 and ADR-130 Amendment 2 for the new provenance: a staged element in two datasets,
    read by a case on one of them, comes back with `sources_withheld` and no source at all (no
    load, no list row, no locator); a case on both is named every one."""
    written: list[NodeWrite | EdgeWrite] = []
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _load(graph, written, two_datasets=True)
        node_ids = [w.id for w in written if isinstance(w, NodeWrite)]
        edge_ids = [w.id for w in written if isinstance(w, EdgeWrite)]
        one = LOADER.model_copy(update={"datasets": [SHARED]})
        both = LOADER.model_copy(update={"datasets": [DATASET, SHARED]})
        for reader, withheld in ((one, True), (both, False)):
            nodes = await graph.get_nodes(node_ids, reader)
            edges = await graph.get_edges(edge_ids, reader)
            assert nodes and edges
            for element in [*nodes, *edges]:
                assert element.provenance.sources_withheld is withheld, element.id
                if withheld:
                    assert element.provenance.sources == []
                    assert "ld-vb-1" not in element.model_dump_json()
                    assert "reference_list:" not in element.model_dump_json()
                else:
                    assert element.provenance.sources
