"""The corpus-wide resolution run and the analyst layer (ADR-143 Amendment 1; the lane-reviewer's
blocker 2 on L3.1), against real ArcadeDB.

A manual split is now written in the case's analyst layer. The run reads every `NOT_SAME_AS` under
its service principal, which reads every dataset; were it to honour a layer's split, case A's
private decision would stop a `SAME_AS` being written in the source that case B reads. So the run
honours a split only when it is in a dataset other than a layer: a split in the source is honoured
as before. One only in a layer is left to its own case's projection, which always honours it
(`01_DOMAIN_MODEL.md` §4), and the conflict is recorded for review on that split, so in that
layer, for that case only (ADR-025 Amendment 1, the owner's ruling of 7 November 2026).

What a mistake here would do, and the case that catches it:

- a layer's split blocking the source's merge for every case, its conflict going unrecorded, or
  case A's own projection then merging the pair:
  `test_a_split_only_in_a_layer_does_not_stop_the_runs_same_as`, and its red half with
  `honoured_splits` planted to honour every split;
- the fix letting a source split through too:
  `test_a_split_in_the_source_still_stops_the_runs_same_as`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.resolve import trigger
from services.resolve.projection import THRESHOLD_BALANCED, compute_clusters
from services.resolve.trigger import run_resolution_for_entity_type
from tests.resolve.test_trigger import CLEARED, _handling, _person_write

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    ExpandRequest,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

SOURCE = "source-dataset"
LAYER_A = "analyst-layer-case-a"


async def _layers() -> set[str]:
    return {LAYER_A}


LAYER_B = "analyst-layer-case-b"
CASE_A = Principal(
    id="analyst-a", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, LAYER_A]
)
CASE_B = Principal(
    id="analyst-b", clearance="OFFICIAL", org_unit="unit-1", datasets=[SOURCE, LAYER_B]
)


async def _clusters(graph: Any, ids: list[str], reader: Principal) -> set[str]:
    """The pair's clusters as `reader`'s projection draws them (what the canvas collapses)."""
    seen = await graph.expand(
        ExpandRequest(node_ids=ids, depth=1, edge_types=["SAME_AS", "NOT_SAME_AS"]), reader
    )
    same = [e for e in seen.edges if e.type == "SAME_AS"]
    split = [e for e in seen.edges if e.type == "NOT_SAME_AS"]
    clusters = compute_clusters(ids, same, split, THRESHOLD_BALANCED)
    return {clusters[i] for i in ids}


async def _run_with_split_in(dataset: str) -> tuple[int, int, int, int]:
    """The run's (`SAME_AS` written, conflicts recorded), then how many clusters the pair is in
    under case A and under case B."""
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        dup_a, dup_b = (
            _person_write("Mercer", "Dana", "1980-01-01").model_copy(update={"datasets": [SOURCE]})
            for _ in range(2)
        )
        a_id, b_id = await graph.upsert_nodes([dup_a, dup_b], tx)
        await graph.upsert_edges(
            [
                EdgeWrite(
                    id=new_id(),
                    type="NOT_SAME_AS",
                    source=a_id,
                    target=b_id,
                    properties={},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[
                            SourceRef(
                                document_id=f"manual:{a_id}:{b_id}", locator="a", excerpt_hash=""
                            )
                        ],
                        first_seen=datetime.now(UTC),
                    ),
                    handling=_handling(),
                    created_by=CLEARED.id,
                    created_at=datetime.now(UTC),
                    datasets=[dataset],
                )
            ],
            tx,
        )
        await graph.commit_transaction(tx)

        tx = await graph.begin_transaction()
        result = await run_resolution_for_entity_type(
            "Person",
            graph=graph,
            tx=tx,
            ontology=ontology,
            scheme=scheme,
            analyst_layers=_layers,
        )
        await graph.commit_transaction(tx)
        in_a = await _clusters(graph, [a_id, b_id], CASE_A)
        in_b = await _clusters(graph, [a_id, b_id], CASE_B)
        return result.same_as_written, result.conflicts_recorded, len(in_a), len(in_b)


async def test_a_split_only_in_a_layer_does_not_stop_the_runs_same_as() -> None:
    """The source's `SAME_AS` is written; the conflict is recorded (on A's split, in A's layer);
    case A still sees the pair apart, case B sees it merged."""
    assert await _run_with_split_in(LAYER_A) == (1, 1, 2, 1)


async def test_the_layer_check_fails_with_every_split_honoured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15: `honoured_splits` planted to the identity, as the run read splits before the
    layer, and the same measurement shows case B's merge stopped by A's private split."""
    monkeypatch.setattr(trigger, "honoured_splits", lambda edges, layers: edges)
    assert await _run_with_split_in(LAYER_A) != (1, 1, 2, 1)


async def test_a_split_in_the_source_still_stops_the_runs_same_as() -> None:
    assert await _run_with_split_in(SOURCE) == (0, 1, 2, 2)
