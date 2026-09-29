"""Writes `SameAsCandidate`s (`resolver.py`) as `SAME_AS` edges through `GraphPort` —
`01_DOMAIN_MODEL.md` §4: "Splink runs over the source-fidelity nodes and writes `SAME_AS` edges
carrying the Fellegi-Sunter match probability, the model version, and the comparison vector that
produced the score." Follows the exact pattern `services/geocoder/match.py` already established
for writing an inferred `SAME_AS` edge through this same port — same identity minting
(`conduit_common.identity`), same `Provenance.state = inferred`, same "no document, so a
synthetic `SourceRef`" shape.

`record_conflicts` (Phase 6 Stage 5) is the second writer here — `conflicts.py`'s own docstring
has the full reasoning for why a detected conflict is a `supersede_edge` of the existing
`NOT_SAME_AS` edge rather than a new edge of its own.
"""

from __future__ import annotations

from collections.abc import Sequence

from conduit_common.identity import new_edge_id, now_utc
from ontology.handling import HandlingScheme
from ports.graph import GraphPort
from schemas.domain import (
    Edge,
    EdgeId,
    EdgeWrite,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
    TxId,
)

from .conflicts import ResolutionConflict, conflict_properties
from .resolver import MODEL_VERSION, SameAsCandidate, comparison_vector_json


async def write_same_as_edges(
    graph: GraphPort,
    candidates: Sequence[SameAsCandidate],
    nodes_by_id: dict[str, Node],
    *,
    created_by: str,
    tx: TxId,
    scheme: HandlingScheme,
) -> list[EdgeId]:
    """`nodes_by_id` supplies each candidate pair's `Handling` — the edge inherits whichever
    endpoint's classification ranks more restrictive under `scheme` (`06_DECISIONS.md` ADR-025: "a
    derived edge should never be more visible than either fact it connects"), taken wholesale
    rather than merged field by field, the same "one endpoint's own handling" shape
    `services/geocoder/match.py` already established for an inferred `SAME_AS` edge with no
    handling of its own to carry — just the more restrictive endpoint, not always `node_a`'s.
    Deterministic identifiers never reach this function at all (`01_DOMAIN_MODEL.md` §4: "Only run
    Splink on types where identity is genuinely uncertain") — it only ever receives what
    `resolver.py` already scored."""
    now = now_utc()
    writes = [
        EdgeWrite(
            id=new_edge_id(),
            type="SAME_AS",
            source=candidate.node_a,
            target=candidate.node_b,
            properties={
                "score": candidate.score,
                "model_version": MODEL_VERSION,
                "comparison_vector": comparison_vector_json(candidate),
            },
            provenance=Provenance(
                state=ProvenanceState.INFERRED,
                sources=[
                    SourceRef(
                        document_id=f"splink:{candidate.node_a}:{candidate.node_b}",
                        locator=MODEL_VERSION,
                        excerpt_hash="",
                    )
                ],
                first_seen=now,
                extraction_confidence=candidate.score,
            ),
            handling=_handling_for(candidate, nodes_by_id, scheme),
            created_by=created_by,
            created_at=now,
        )
        for candidate in candidates
    ]
    if not writes:
        return []
    return await graph.upsert_edges(writes, tx)


def _handling_for(
    candidate: SameAsCandidate, nodes_by_id: dict[str, Node], scheme: HandlingScheme
) -> Handling:
    node_a = nodes_by_id[candidate.node_a]
    node_b = nodes_by_id[candidate.node_b]
    rank = {classification: i for i, classification in enumerate(scheme.classification)}
    if rank[node_b.handling.classification] > rank[node_a.handling.classification]:
        return node_b.handling
    return node_a.handling


async def record_conflicts(
    graph: GraphPort,
    conflicts: Sequence[ResolutionConflict],
    not_same_as_edges_by_id: dict[EdgeId, Edge],
    *,
    created_by: str,
    tx: TxId,
) -> list[EdgeId]:
    """Annotates each conflicting `NOT_SAME_AS` edge via `supersede_edge` — `conflicts.py`'s own
    docstring has the full reasoning for why this is a supersede of the existing split edge rather
    than a new edge or record type. `not_same_as_edges_by_id` is the caller's job to have already
    fetched (the same edges `detect_conflicts` was run against), so this function does no
    `GraphPort` reads itself, only the one write per conflict."""
    now = now_utc()
    superseded_ids: list[EdgeId] = []
    for conflict in conflicts:
        edge = not_same_as_edges_by_id[conflict.not_same_as_edge_id]
        replacement = EdgeWrite(
            id=new_edge_id(),
            type=edge.type,
            source=edge.source,
            target=edge.target,
            properties={**edge.properties, **conflict_properties(conflict)},
            interval=edge.interval,
            occurrences=edge.occurrences,
            provenance=edge.provenance,
            handling=edge.handling,
            created_by=created_by,
            created_at=now,
        )
        superseded_ids.append(await graph.supersede_edge(edge.id, replacement, tx))
    return superseded_ids
