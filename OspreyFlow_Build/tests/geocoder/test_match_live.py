"""`services/geocoder/match.py` against a real ArcadeDB — `tests/geocoder/
test_match.py`'s fake-`GraphPort` tests cannot catch an ontology
schema-validation rejection, and one genuinely existed here: found live,
not by inspection, while first verifying this module by hand.
`packages/ontology/loader.py`'s system `SAME_AS` edge type declared no
`properties` at all, so `GraphPort.upsert_edges`'s own real
ontology-validation layer (`packages/ontology/validation.py`) rejected the
`score` property this module writes — a gap no previous `SAME_AS` writer
had ever been built to trip over. Fixed in `loader.py`
(`_SYSTEM_EDGE_PROPERTIES`); this test is what would have caught it
automatically, kept here so it cannot silently regress.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.geocoder.match import match_place_mention

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    ResolutionState,
    SourceRef,
)

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


async def test_writes_a_real_same_as_edge_the_ontology_accepts() -> None:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    now = datetime.now(UTC)
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )

    async with arcadedb_adapter(ontology, scheme) as graph:
        mention_id, candidate_id = new_id(), new_id()
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(
            [
                NodeWrite(
                    id=mention_id, type="Location", properties={"name": "Cranford"},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[SourceRef(document_id="test", locator="x", excerpt_hash="")],
                        first_seen=now,
                    ),
                    handling=handling, resolution=ResolutionState(),
                    created_by=CLEARED.id, created_at=now,
                ),
                NodeWrite(
                    id=candidate_id, type="Location",
                    properties={"name": "Cranford", "osm_id": "test-osm-live-1"},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[SourceRef(document_id="test", locator="y", excerpt_hash="")],
                        first_seen=now,
                    ),
                    handling=handling, resolution=ResolutionState(),
                    created_by=CLEARED.id, created_at=now,
                ),
            ],
            tx,
        )
        await graph.commit_transaction(tx)

        mention = await graph.get_node(mention_id, CLEARED)
        candidate = await graph.get_node(candidate_id, CLEARED)
        assert mention is not None
        assert candidate is not None

        tx2 = await graph.begin_transaction()
        edge = await match_place_mention(graph, mention, [candidate], CLEARED, scheme, tx2)
        await graph.commit_transaction(tx2)

        assert edge is not None
        assert edge.type == "SAME_AS"
        assert edge.properties["score"] == 1.0
