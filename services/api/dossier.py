"""Dossier document assembly — `docs/08_ACCEPTANCE_SCENARIOS.md` B6: "Message content renders
with the entity spans highlighted in place."

**Accepted candidates only, deliberately.** `09_INGEST_STUDIO.md` §7's own review queue (pending
candidates awaiting accept/reject) is a different, still-unbuilt screen — B6 is post-hoc
inspection of an already-resolved message, not candidate triage, so a `pending` or `rejected`
candidate's span never appears here. A pending candidate has no graph node at all
(`services/api/review.py`'s own accept-time node-minting) and therefore no `Handling` to check
visibility against — it is not merely out of scope, it is not a coherent case.

**The same existence-leak question Stage 3 answered for `explain` rows, one surface over.** A
span whose resolved node fails `narrow_to_visible` is dropped from the response entirely, never
returned in a redacted form — a redacted span still asserts "something was extracted here," the
exact signal `visiblePairs` (Stage 3, the Glass side) already exists to avoid. `narrow_to_visible`
(`services/api/access.py`) is the same function `set_resolution_threshold`/`explain_cluster`
already use — this module is disclosed as its third caller, not a fourth independent copy of the
pattern.
"""

from __future__ import annotations

import re

from pydantic import BaseModel
from services.api.access import narrow_to_visible
from services.api.review import CandidateStatus, ExtractionCandidateStore

from ports.graph import GraphPort
from schemas.domain import NodeId, Principal, ProvenanceState

#: `services/extract/candidates.py`'s own `_locate` produces exactly this shape. Anything else —
#: an audio timestamp, a row index — has no in-place text position to highlight; a locator this
#: doesn't match is a fact about the source type, not a defect, and the span is silently dropped.
_CHAR_SPAN = re.compile(r"^char span (\d+)-(\d+)$")


class MessageSpan(BaseModel):
    start: int
    end: int
    node_id: NodeId
    entity_type: str
    #: Mirrors `canvas/nodeAttributes.ts`'s own `provenanceStroke` distinction (solid/dashed for
    #: asserted/inferred) rather than inventing a second visual language for the same fact.
    provenance_state: ProvenanceState


class DocumentView(BaseModel):
    document_id: str
    text: str
    spans: list[MessageSpan]


def _parse_char_span(locator: str) -> tuple[int, int] | None:
    match = _CHAR_SPAN.match(locator)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


async def get_document_view(
    candidates: ExtractionCandidateStore,
    graph: GraphPort,
    document_id: str,
    principal: Principal,
) -> DocumentView:
    text = await candidates.get_document_text(document_id, principal)
    records = await candidates.list_for_document(document_id, principal)
    accepted = [
        record
        for record in records
        if record.status is CandidateStatus.ACCEPTED and record.node_id is not None
    ]

    node_ids = [record.node_id for record in accepted if record.node_id is not None]
    result = await narrow_to_visible(graph, node_ids, principal)

    spans: list[MessageSpan] = []
    for record in accepted:
        node = result.nodes.get(record.node_id) if record.node_id else None
        if node is None:
            continue
        parsed = _parse_char_span(record.locator)
        if parsed is None:
            continue
        start, end = parsed
        spans.append(
            MessageSpan(
                start=start,
                end=end,
                node_id=node.id,
                entity_type=record.entity_type,
                provenance_state=node.provenance.state,
            )
        )
    spans.sort(key=lambda span: span.start)
    return DocumentView(document_id=document_id, text=text, spans=spans)
