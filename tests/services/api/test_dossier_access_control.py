"""Standing rule 2, applied to the Dossier's own document assembly (`services/api/dossier.py`,
`GET .../dossier/documents/{document_id}`, Phase 6a Stage 4, B6) — the same existence-leak
question Stage 3 answered for `explain` rows (`test_explain_cluster_access_control.py`), one
surface over: a message's own text can mention an entity the calling principal is not cleared to
see, and the highlighted span must not disclose that it was ever extracted.

Uses the **real** `graph_arcadedb` adapter, for the same reason every other access-control test in
this package does: a fake's own simulated filtering could drift from the real adapter's. Also uses
the **real** `ExtractionCandidateStore` (Postgres) — the accept-then-mark-reviewed flow this test
drives is exactly `accept_candidate`'s own shape, not reimplemented.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from conduit_common.identity import new_id, new_node_id, now_utc
from services.api.config import PostgresConfig
from services.api.dossier import get_document_view
from services.api.review import CandidateStatus, ExtractionCandidateStore
from services.extract.candidates import ExtractionCandidate

from ontology.handling import load_uk_le_scheme
from schemas.domain import NodeWrite, Principal, Provenance, ProvenanceState, SourceRef

from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

SHARED_UNIT = "unit-1"
OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit=SHARED_UNIT)
SECRET = Principal(id="analyst-secret", clearance="SECRET", org_unit=SHARED_UNIT)

MESSAGE_TEXT = "Dana called Owen about the shipment."
#: `Dana` at 0-4, `Owen` at 13-17 — real character offsets into `MESSAGE_TEXT` above, the same
#: `"char span N-M"` shape `services/extract/candidates.py`'s own `_locate` produces.
DANA_LOCATOR = "char span 0-4"
OWEN_LOCATOR = "char span 13-17"


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime.now(UTC),
    )


def _handling(classification: str) -> dict[str, str | None]:
    return {
        "classification": classification,
        "handling_code": "P",
        "originator": SHARED_UNIT,
        "owning_unit": SHARED_UNIT,
        "action_code": None,
        "sanitisation_code": None,
    }


def _node_write(classification: str, family_name: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": family_name},
        provenance=_provenance(),
        handling=_handling(classification),  # type: ignore[arg-type]
        created_by="loader-1",
        created_at=now_utc(),
    )


def _candidate(document_id: str, locator: str) -> ExtractionCandidate:
    return ExtractionCandidate(
        id=new_id(),
        document_id=document_id,
        entity_type="Person",
        properties={},
        confidence=0.9,
        model="qwen2.5:0.5b-instruct",
        locator=locator,
        excerpt_hash="irrelevant-here",
        handling=_handling("OFFICIAL"),  # type: ignore[arg-type]
    )


@pytest.fixture
async def candidates():
    store = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


async def test_a_span_naming_a_hidden_entity_is_omitted_not_redacted(
    factory: GraphAdapterFactory, candidates: ExtractionCandidateStore
) -> None:
    async with factory.context() as graph:
        visible_write = _node_write("OFFICIAL", "Dana")
        hidden_write = _node_write("SECRET", "Owen")
        tx = await graph.begin_transaction()
        (visible_id, hidden_id) = await graph.upsert_nodes([visible_write, hidden_write], tx)
        await graph.commit_transaction(tx)

        document_id = new_id()
        await candidates.store_document_text(document_id, MESSAGE_TEXT, OFFICIAL)
        (visible_record, hidden_record) = await candidates.store(
            [
                _candidate(document_id, DANA_LOCATOR),
                _candidate(document_id, OWEN_LOCATOR),
            ],
            OFFICIAL,
        )
        await candidates.mark_reviewed(
            visible_record.id, OFFICIAL, status=CandidateStatus.ACCEPTED, node_id=visible_id
        )
        await candidates.mark_reviewed(
            hidden_record.id, OFFICIAL, status=CandidateStatus.ACCEPTED, node_id=hidden_id
        )

        official_view = await get_document_view(candidates, graph, document_id, OFFICIAL)
        assert official_view.text == MESSAGE_TEXT
        assert [span.node_id for span in official_view.spans] == [visible_id]
        assert hidden_id not in [span.node_id for span in official_view.spans]

        secret_view = await get_document_view(candidates, graph, document_id, SECRET)
        assert {span.node_id for span in secret_view.spans} == {visible_id, hidden_id}


async def test_a_pending_candidate_never_appears_as_a_span(
    factory: GraphAdapterFactory, candidates: ExtractionCandidateStore
) -> None:
    """A pending candidate has no graph node at all — not merely out of scope, not a coherent
    case (`services/api/dossier.py`'s own module docstring)."""
    async with factory.context() as graph:
        document_id = new_id()
        await candidates.store_document_text(document_id, MESSAGE_TEXT, OFFICIAL)
        await candidates.store([_candidate(document_id, DANA_LOCATOR)], OFFICIAL)

        view = await get_document_view(candidates, graph, document_id, OFFICIAL)

        assert view.spans == []
