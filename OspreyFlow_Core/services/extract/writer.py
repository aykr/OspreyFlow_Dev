"""Writes accepted candidates as graph nodes, and the confirm/retract pair that promotes an
already-graph-resident `inferred` node to `asserted` (or reverses that) — `01_DOMAIN_MODEL.md`
§2.1, `09_INGEST_STUDIO.md` §7.

**Accept ≠ confirm.** `write_candidate` writes `provenance.state = inferred`, never `asserted` —
accepting a review-queue candidate means "let this exist in the graph as a first-class, honestly
model-attributed entity", not "I attest this is true". Writing it straight to `asserted` would be
exactly the automatic promotion this codebase forbids, dressed up as a queue action instead
of a confidence threshold; it would also make the Phase 6 exit criterion's own "extracted entities
appear as `inferred`" unreachable for anything that had passed through the review queue at all.
Confirmation is `confirm_node`, a separate, later, explicit action, exactly as
`01_DOMAIN_MODEL.md` §2.1 describes it.

**Confirm/retract go through `GraphPort.supersede_node`, not a new primitive.** This was not
invented for this module: `packages/ports/graph.py`'s own `supersede_node` docstring already names
"Phase 6's retraction" as one of its two intended callers (the other being "Phase 8's
judgement-review loop"), written well before this stage existed. `supersede_node` is also the only
mutation primitive `GraphPort` has for an *existing* element — `upsert_nodes` is for new ones —
so there was never a second reasonable choice once a node's own `provenance.state` needs to change
after it has already been written.

**Retract is not `GraphPort.revert_elements`.** That primitive permanently hides an element from
every future read, any principal, audit trail intact — the mechanism `services/ingest`'s
`revert_load` uses for reverting a whole load. Retracting a confirmation is a much lighter action:
"this is no longer an asserted fact", not "this should never have existed". A retracted node stays
exactly as visible as it was before it was ever confirmed — because `inferred` is exactly what it
was before confirmation, and retract's whole job is putting it back there.

**Retract always reverts to `inferred`, never attempts to restore `unresolved`.** Both `inferred`
and `unresolved` are non-asserted states `confirm_node` accepts promoting from, but nothing on the
node itself records which of the two it was before a confirmation — reconstructing that would need
a new field nothing here has a use for otherwise. `inferred` is the conservative, honest choice: it
says "not a confirmed fact", which is the only thing retraction is actually asserting.

**Edge confirm is built for one caller only** (ADR-109 Amendment 7): `confirm_edge` below takes a
link the caller has already read *as the reader* — a screening alert's cited `SAME_AS`, from
`edges_among` — so it needs no `get_edge`. A general edge confirm/retract route is still not built:
`GraphPort` has no `get_edge` method — there is
no way to fetch an existing edge's current state before deciding whether a requested transition is
valid, and adding one is a real port change needing its own conformance-suite coverage first,
not a small addition folded in here. This is deferred alongside edge/relationship
candidate extraction itself (`candidates.py`'s own module docstring — "Proposed links" in
`09_INGEST_STUDIO.md` §7's mockup), which is the only thing that would produce an inferred edge
needing this in the first place.
"""

from __future__ import annotations

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import sources_in_full
from ports.graph import GraphPort
from schemas.domain import (
    Edge,
    EdgeId,
    EdgeWrite,
    Node,
    NodeId,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    TxId,
)

from .candidates import ExtractionCandidate


class NodeNotFoundError(Exception):
    """Raised by `confirm_node`/`retract_node` when `GraphPort.get_node` returns `None` — either
    no such node exists, or `principal` cannot see it. Deliberately the same outcome either way,
    the existence-leak discipline `00_ARCHITECTURE.md` §5 requires everywhere else in this build."""


class ProvenanceTransitionError(Exception):
    """Raised when the target node's current `provenance.state` does not allow the requested
    transition — confirming an already-`asserted` node, or retracting one that was never
    confirmed. Both are caller mistakes worth surfacing distinctly, not silent no-ops."""


async def write_candidate(
    graph: GraphPort, candidate: ExtractionCandidate, *, created_by: str, tx: TxId
) -> NodeId:
    """Writes one accepted `ExtractionCandidate` as a new, `inferred` graph node. `candidate.
    handling` was fixed at extraction-run time (the caller's own `defaults`-style choice, the same
    shape a structured recipe's `defaults.handling` already is) — accept does not renegotiate it
    per candidate."""
    now = now_utc()
    write = NodeWrite(
        id=new_node_id(),
        type=candidate.entity_type,
        properties=candidate.properties,
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[
                SourceRef(
                    document_id=candidate.document_id,
                    locator=candidate.locator,
                    excerpt_hash=candidate.excerpt_hash,
                )
            ],
            extracted_by=f"model:{candidate.model}",
            extraction_confidence=candidate.confidence,
            first_seen=now,
        ),
        handling=candidate.handling,
        created_by=created_by,
        created_at=now,
    )
    (node_id,) = await graph.upsert_nodes([write], tx)
    return node_id


def _replacement_for(node: Node, principal: Principal, *, new_state: ProvenanceState) -> NodeWrite:
    now = now_utc()
    confirming = new_state is ProvenanceState.ASSERTED
    provenance = node.provenance.model_copy(
        update={
            "state": new_state,
            "confirmed_by": principal.id if confirming else None,
            "last_confirmed": now if confirming else None,
            # `Provenance`'s own validator forbids a non-null `extraction_confidence` on asserted
            # provenance (`01_DOMAIN_MODEL.md` §2.1) — confirming must clear it, not merely change
            # `state` and leave a stale model-reported figure sitting on a now-human-attested fact.
            # Retracting does not attempt to restore it: nothing preserves the original value once
            # cleared, and `writer.py`'s own module docstring already accepts that retract reverts
            # to `inferred` honestly, not to a reconstructed prior state.
            "extraction_confidence": None,
        }
    )
    return NodeWrite(
        # A fresh id, not `node.id` — found live, not assumed: `GraphPort.supersede_node`'s own
        # conformance suite (`tests/conformance/graph_port/test_suite.py`) asserts `new_id !=
        # old_id`, and reusing the original id collides with the still-present superseded
        # revision's own index entry (confirmed directly against a real ArcadeDB: "duplicate key
        # ... already assigned to record"). `supersede_node`'s own docstring already says as much
        # — "returns that new id" — this was a genuine bug in the first draft of this function,
        # not a design choice.
        id=new_node_id(),
        type=node.type,
        properties=node.properties,
        provenance=provenance,
        handling=node.handling,
        resolution=node.resolution,
        created_by=principal.id,
        created_at=now,
    )


async def confirm_node(
    graph: GraphPort, node_id: NodeId, principal: Principal, *, tx: TxId
) -> NodeId:
    """`01_DOMAIN_MODEL.md` §2.1: "Confirmation is an explicit analyst action that writes
    `confirmed_by` and `last_confirmed` and flips the state to `asserted`." Valid from `inferred`
    or `unresolved`; a no-op attempt against an already-`asserted` node raises rather than silently
    succeeding, since a caller asking to confirm something already confirmed most likely has a
    stale view of it."""
    # In full: the replacement is built from this node's own provenance (ADR-130 Amendment 2).
    with sources_in_full():
        node = await graph.get_node(node_id, principal)
    if node is None:
        raise NodeNotFoundError(node_id)
    if node.provenance.state is ProvenanceState.ASSERTED:
        raise ProvenanceTransitionError(f"{node_id} is already asserted")
    replacement = _replacement_for(node, principal, new_state=ProvenanceState.ASSERTED)
    return await graph.supersede_node(node_id, replacement, tx)


async def confirm_edge(graph: GraphPort, edge: Edge, principal: Principal, *, tx: TxId) -> EdgeId:
    """An inferred link, already read as `principal`, made asserted by that person: a new revision
    naming who confirmed it and when, the model's figure cleared (as `confirm_node` does)."""
    if edge.provenance.state is ProvenanceState.ASSERTED:
        raise ProvenanceTransitionError(f"{edge.id} is already asserted")
    now = now_utc()
    provenance = edge.provenance.model_copy(
        update={"state": ProvenanceState.ASSERTED, "confirmed_by": principal.id,
                "last_confirmed": now, "extraction_confidence": None}
    )  # fmt: skip
    replacement = EdgeWrite(
        id=new_edge_id(), type=edge.type, source=edge.source, target=edge.target,
        properties=edge.properties, interval=edge.interval, occurrences=edge.occurrences,
        basis=edge.basis, provenance=provenance, handling=edge.handling,
        created_by=principal.id, created_at=now,
    )  # fmt: skip
    return await graph.supersede_edge(edge.id, replacement, tx)


async def retract_node(
    graph: GraphPort, node_id: NodeId, principal: Principal, *, tx: TxId
) -> NodeId:
    """The mirror of `confirm_node` — valid only from `asserted`, since retracting a node that was
    never confirmed is the same caller mistake as confirming one that already is."""
    # In full: the replacement is built from this node's own provenance (ADR-130 Amendment 2).
    with sources_in_full():
        node = await graph.get_node(node_id, principal)
    if node is None:
        raise NodeNotFoundError(node_id)
    if node.provenance.state is not ProvenanceState.ASSERTED:
        raise ProvenanceTransitionError(f"{node_id} is not asserted")
    replacement = _replacement_for(node, principal, new_state=ProvenanceState.INFERRED)
    return await graph.supersede_node(node_id, replacement, tx)
