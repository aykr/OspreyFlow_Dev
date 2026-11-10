"""A fuzzy match's SAME_AS through the real ArcadeDB adapter (ADR-006 Amendment 1; ADR-140 decision
13; rules 3, 4, 5 and 6). The offline cases (`test_fuzzy_match.py`) prove what the engine hands the
graph; this proves the store keeps it: the visitor and the owner it matched stay two nodes in storage,
joined by one SAME_AS stored `inferred` with its score; a second load leaves it inferred; only a
person's confirmation (`services/extract/writer.confirm_edge`, `confirm_inferred`'s write) makes it
asserted; and a reader of another dataset reads none of it (rule 4).

Live: run under a lease (`stack_lease.sh acquire studio …`, the ports it prints pinned); the staged
Parquet goes to a temporary directory, so no object store is touched.
"""

from __future__ import annotations

from typing import Any

from services.api.dataset_scope import DatasetStampingGraph
from services.extract.writer import confirm_edge
from services.ingest.staged_run import run_staged_recipe
from services.ingest.staging import ObjectStorageConfig

from adapters.graph_arcadedb.testing import arcadedb_adapter
from schemas.domain import EdgeWrite, NodeWrite, Principal, ProvenanceState
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_fuzzy_match import ONTOLOGY, SCHEME, _recipe, _sources

DATASET = "pid"
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1", datasets=[DATASET])
ANALYST = Principal(id="analyst-1", clearance="SECRET", org_unit="unit-1", datasets=[DATASET])
ELSEWHERE = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1", datasets=["ledger"])


async def _load(graph: Any, written: list[NodeWrite | EdgeWrite], load_id: str) -> Any:
    stamping: Any = DatasetStampingGraph(graph, dataset=DATASET)
    tx = await stamping.begin_transaction()
    done = await run_staged_recipe(
        _recipe(0.6), sources=_sources(), lists={}, dataset_id=DATASET, graph=stamping,
        ontology=ONTOLOGY, tx=tx, principal=LOADER, load_id=load_id,
        investigation_scope="case-live-8", storage=ObjectStorageConfig(bucket="staging"),
        scheme=SCHEME, written=written, subscribed=(),
    )  # fmt: skip
    await stamping.commit_transaction(tx)
    return done


async def test_the_match_is_two_nodes_and_one_inferred_same_as_in_storage() -> None:
    written: list[NodeWrite | EdgeWrite] = []
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _load(graph, written, "ld-fz-1")
        links = [w for w in written if isinstance(w, EdgeWrite) and w.type == "SAME_AS"]
        assert len(links) == 3
        stored = await graph.get_edges([w.id for w in links], LOADER)
        assert len(stored) == 3
        for link in stored:
            assert link.source != link.target
            assert link.provenance.state is ProvenanceState.INFERRED
            assert 0.6 <= link.properties["score"] < 1
        ends = await graph.get_nodes([stored[0].source, stored[0].target], LOADER)
        assert len(ends) == 2 and all(n.type == "Person" for n in ends)

        # A second load of the same rows promotes nothing (rule 5).
        again: list[NodeWrite | EdgeWrite] = []
        await _load(graph, again, "ld-fz-2")
        relinks = [w for w in again if isinstance(w, EdgeWrite) and w.type == "SAME_AS"]
        restored = await graph.get_edges([w.id for w in relinks], LOADER)
        assert restored and {e.provenance.state for e in restored} == {ProvenanceState.INFERRED}

        # A person's confirmation, and only that, makes it fact, naming them.
        tx = await graph.begin_transaction()
        confirmed_id = await confirm_edge(graph, stored[0], ANALYST, tx=tx)
        await graph.commit_transaction(tx)
        [confirmed] = await graph.get_edges([confirmed_id], ANALYST)
        assert confirmed.provenance.state is ProvenanceState.ASSERTED
        assert confirmed.provenance.confirmed_by == ANALYST.id


async def test_a_reader_of_another_dataset_reads_no_match() -> None:
    """Rule 4: the SAME_AS and the two records it joins are the loading dataset's."""
    written: list[NodeWrite | EdgeWrite] = []
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _load(graph, written, "ld-fz-3")
        links = [w.id for w in written if isinstance(w, EdgeWrite) and w.type == "SAME_AS"]
        nodes = [w.id for w in written if isinstance(w, NodeWrite)]
        assert links and nodes
        assert await graph.get_edges(links, ELSEWHERE) == []
        assert await graph.get_nodes(nodes, ELSEWHERE) == []
