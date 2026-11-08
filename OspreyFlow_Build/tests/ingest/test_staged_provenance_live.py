"""A Join's provenance, written by the real Map write and read back through the real ArcadeDB
adapter (the orchestrator's settlement of 8 November 2026, Q2 (a): one `SourceRef` per input row in
the element's existing `provenance.sources`, a Join giving two, with no adapter change).

The offline cases (`test_staged_run.py`) prove what the engine hands the graph; this proves the
store keeps it: an adapter that dropped the new `row_key`/`load_id`, or kept only the first source,
would pass offline and fail here. Live: run under a lease (`stack_lease.sh acquire studio …`, the
ports it prints pinned); the staged Parquet goes to a temporary directory, so no object store is
touched.
"""

from __future__ import annotations

from adapters.graph_arcadedb.testing import arcadedb_adapter
from schemas.domain import EdgeWrite, NodeWrite
from services.ingest.staged_run import run_staged_recipe
from services.ingest.staging import ObjectStorageConfig
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_staged_run import LOADER, ONTOLOGY, RECIPE, SCHEME, inputs


async def test_a_join_s_two_sides_are_stored_on_the_link_and_read_back() -> None:
    sources, lists = inputs()
    written: list[NodeWrite | EdgeWrite] = []
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        tx = await graph.begin_transaction()
        done = await run_staged_recipe(
            RECIPE,
            sources=sources,
            lists=lists,
            dataset_id="pid",
            graph=graph,
            ontology=ONTOLOGY,
            tx=tx,
            principal=LOADER,
            load_id="ld-live-1",
            investigation_scope="case-live-1",
            storage=ObjectStorageConfig(bucket="staging"),
            scheme=SCHEME,
            written=written,
        )
        await graph.commit_transaction(tx)
        assert done.report.edges_created > 0

        owner = await graph.find_node("Person", "family_name", "WHITLOW", LOADER)
        assert owner is not None
        [stored_owner] = await graph.get_nodes([owner.id], LOADER)
        stored = {
            (s.document_id, s.locator, s.load_id): s.row_key for s in stored_owner.provenance.sources
        }
        assert ("visit_bookings", "row 0", "ld-vb-1") in stored
        assert ("number_owners", "row 0", "ld-no-1") in stored
        assert all(stored.values()), stored

        uses_ids = [
            w.id for w in written if isinstance(w, EdgeWrite) and w.type == "USES" and w.source == owner.id
        ]
        assert uses_ids
        [link] = await graph.get_edges(uses_ids[:1], LOADER)
        sides = {(s.document_id, s.load_id) for s in link.provenance.sources}
        assert {("visit_bookings", "ld-vb-1"), ("number_owners", "ld-no-1")} <= sides
        assert all(s.row_key for s in link.provenance.sources)
