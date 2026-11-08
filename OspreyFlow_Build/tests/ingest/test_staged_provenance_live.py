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

from adapters.graph_arcadedb.testing import arcadedb_adapter
from schemas.domain import EdgeWrite, NodeWrite, Principal
from services.api.dataset_scope import DatasetStampingGraph
from services.ingest.staged_run import run_staged_recipe
from services.ingest.staging import ObjectStorageConfig
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_staged_run import ONTOLOGY, RECIPE, SCHEME, inputs

DATASET = "pid_live"
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1", datasets=[DATASET])
ELSEWHERE = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1", datasets=["ledger_live"])


async def _load(graph: Any, written: list[NodeWrite | EdgeWrite]) -> Any:
    sources, lists = inputs()
    stamping = DatasetStampingGraph(graph, dataset=DATASET)
    tx = await stamping.begin_transaction()
    done = await run_staged_recipe(
        RECIPE,
        sources=sources,
        lists=lists,
        dataset_id="pid",
        graph=stamping,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx=tx,
        principal=LOADER,
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
        assert {("visit_bookings", "row 0", "ld-vb-1"), ("number_owners", "row 0", "ld-no-1")} <= sides
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
