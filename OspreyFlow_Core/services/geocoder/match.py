"""The in-deployment geocoder — matches an extraction-produced
place-mention `Location` against the gazetteer's canonical `Location`,
writing a scored `SAME_AS` edge. Mirrors `spec/01_DOMAIN_MODEL.md` §4's
entity-resolution design exactly: never a merge, a scored edge an analyst
can later confirm (flip to `asserted`) or reject (write a `NOT_SAME_AS`).
`spec/00_ARCHITECTURE.md`'s "Geospatial reference data as entities"
section: "A gazetteer match is `inferred`, like any other derived link...
a resolution decision with a confidence, not a fact. It follows the same
provenance rules as a model extraction and is confirmable by an analyst."

No real caller exists yet — Phase 6's extraction pipeline is the eventual
one (the same "build the capability
before its eventual caller" position `GraphPort`
preceding the Conduit (Phase 3) already took).

**Candidate retrieval is explicitly not this module's job.**
`GraphPort.search_nodes` only does exact identifier match.
`GraphPort.suggest_locations` (Phase 5's known-gaps closure) closes the "no honest way to find
its own candidates" gap this docstring used to record — a coarse, bounded
substring scan over `Location.name`, not full-text/fuzzy matching — but
this function still takes `candidates` from its caller rather than calling
it directly: Phase 6's extraction pipeline is the real eventual caller,
and it is what should own the retrieval-then-score sequencing, not this
scoring-only function reaching backward into `GraphPort` itself.

**Not Splink-grade.** `01_DOMAIN_MODEL.md` §4 describes Splink writing
`SAME_AS` edges "carrying the Fellegi-Sunter match probability, the model
version, and the comparison vector" — `services/resolve/` is that
still-unbuilt Phase 6 job. This module uses stdlib `difflib.
SequenceMatcher.ratio()` on `Location.name` instead: a proportionate
stand-in for demonstrating the match-and-link mechanism, not a claim to
be real entity resolution. The written edge's `properties["score"]` is
this ratio; there is no model version or comparison vector to record.

**`Edge`/`EdgeWrite` has no `resolution` field** — only `Node` does
(`ResolutionState.cluster_score` describes a *node's* confidence in its
own cluster membership, a different, node-level concept). A `SAME_AS`
edge's own match score is a plain edge property, per §4's own prose
("carrying the... probability") rather than a structured field — there
is no fixed schema for it beyond that.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from difflib import SequenceMatcher

from conduit_common.identity import new_id
from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    TxId,
)


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


async def match_place_mention(
    graph: GraphPort,
    mention: Node,
    candidates: Sequence[Node],
    principal: Principal,
    scheme: HandlingScheme,
    tx: TxId,
    *,
    min_score: float = 0.8,
) -> Edge | None:
    """Scores every candidate's `name` property against the mention's own,
    writes a `SAME_AS` edge to the best-scoring one at or above
    `min_score`, and returns it — `None` if nothing scored high enough.

    A candidate the given `principal` cannot view under `scheme` is never
    matched against, exactly the access-control-in-the-adapter discipline
    every other read path in this codebase has,
    applied here even though this is a write path: an inferred link to
    something the calling principal cannot see would itself be a
    disclosure via the edge's own existence.
    """
    mention_name = mention.properties.get("name")
    if not mention_name:
        return None

    visible_candidates = [
        c for c in candidates if principal_may_view(c.handling, principal, scheme)
    ]

    best: Node | None = None
    best_score = 0.0
    for candidate in visible_candidates:
        candidate_name = candidate.properties.get("name")
        if not candidate_name:
            continue
        score = _name_similarity(mention_name, candidate_name)
        if score > best_score:
            best, best_score = candidate, score

    if best is None or best_score < min_score:
        return None

    now = datetime.now(UTC)
    edge_write = EdgeWrite(
        id=new_id(),
        type="SAME_AS",
        source=mention.id,
        target=best.id,
        properties={"score": best_score},
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[
                SourceRef(document_id=f"geocoder:{mention.id}", locator=best.id, excerpt_hash="")
            ],
            first_seen=now,
        ),
        handling=mention.handling,
        created_by=principal.id,
        created_at=now,
    )
    edge_ids = await graph.upsert_edges([edge_write], tx)
    return Edge(
        id=edge_ids[0],
        type=edge_write.type,
        source=edge_write.source,
        target=edge_write.target,
        properties=edge_write.properties,
        provenance=edge_write.provenance,
        handling=edge_write.handling,
        audit=AuditStub(created_at=now, created_by=principal.id),
    )
