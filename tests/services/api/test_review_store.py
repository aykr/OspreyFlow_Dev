"""`services/api/review.py`'s `ExtractionCandidateStore` — direct, live-Postgres correctness,
mirroring `test_studio_recipes_store.py`'s own discipline: the JSON round trip and the
existence-leak behaviour deserve a direct proof rather than only exercise through route-level
fakes. `docs/09_INGEST_STUDIO.md` §7.
"""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.review import (
    CandidateStatus,
    DocumentNotFoundError,
    ExtractionCandidateNotFoundError,
    ExtractionCandidateStore,
)
from services.extract.candidates import ExtractionCandidate

from conduit_common.identity import new_id
from schemas.domain import Handling, Principal

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_UNIT_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


def _candidate(candidate_id: str | None = None, document_id: str = "doc-1") -> ExtractionCandidate:
    """`candidate_id` defaults to a fresh ULID, not a fixed literal — this suite runs against a
    real, persistent Postgres database (no per-test truncation), so a hardcoded id would collide
    with a leftover row from the previous run, the same reason `StudioRecipeStore.create_draft`
    mints its own id rather than accepting a caller-supplied one."""
    return ExtractionCandidate(
        id=candidate_id or new_id(),
        document_id=document_id,
        entity_type="Person",
        properties={"family_name": "MERCER", "given_names": "Dana"},
        confidence=0.9,
        model="qwen2.5:0.5b-instruct",
        locator="char span 0-6",
        excerpt_hash="abc123",
        handling=_handling(),
    )


@pytest.fixture
async def store():
    s = await ExtractionCandidateStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_stored_candidate_round_trips_with_pending_status(
    store: ExtractionCandidateStore,
) -> None:
    (record,) = await store.store([_candidate()], ANALYST)

    assert record.status == CandidateStatus.PENDING
    assert record.owning_unit == "unit-1"
    assert record.created_by == "analyst-1"
    assert record.reviewed_by is None
    assert record.node_id is None

    fetched = await store.get_authorized(record.id, ANALYST)
    assert fetched.properties == {"family_name": "MERCER", "given_names": "Dana"}
    assert fetched.handling == _handling()


async def test_list_for_document_is_scoped_to_owning_unit(store: ExtractionCandidateStore) -> None:
    document_id = new_id()
    (own_record,) = await store.store([_candidate(document_id=document_id)], ANALYST)
    (other_record,) = await store.store([_candidate(document_id=document_id)], OTHER_UNIT_ANALYST)

    own = await store.list_for_document(document_id, ANALYST)
    other = await store.list_for_document(document_id, OTHER_UNIT_ANALYST)

    assert {r.id for r in own} == {own_record.id}
    assert {r.id for r in other} == {other_record.id}


async def test_get_authorized_denies_a_principal_in_a_different_org_unit(
    store: ExtractionCandidateStore,
) -> None:
    """`CLAUDE.md` rule 4: every read path gets its own access-control test. Raises the same
    not-found error as a genuinely missing id — the existence-leak discipline this store's own
    docstring names."""
    (record,) = await store.store([_candidate()], ANALYST)

    with pytest.raises(ExtractionCandidateNotFoundError):
        await store.get_authorized(record.id, OTHER_UNIT_ANALYST)


async def test_get_authorized_raises_for_an_unknown_id(store: ExtractionCandidateStore) -> None:
    with pytest.raises(ExtractionCandidateNotFoundError):
        await store.get_authorized("no-such-candidate", ANALYST)


async def test_mark_reviewed_persists_status_and_node_id(store: ExtractionCandidateStore) -> None:
    (record,) = await store.store([_candidate()], ANALYST)

    await store.mark_reviewed(
        record.id, ANALYST, status=CandidateStatus.ACCEPTED, node_id="node-42"
    )

    fetched = await store.get_authorized(record.id, ANALYST)
    assert fetched.status == CandidateStatus.ACCEPTED
    assert fetched.reviewed_by == "analyst-1"
    assert fetched.reviewed_at is not None
    assert fetched.node_id == "node-42"


async def test_storing_no_candidates_is_a_no_op(store: ExtractionCandidateStore) -> None:
    assert await store.store([], ANALYST) == []


# --- document text (Phase 6a Stage 4, B6 — the Dossier) -----------------------------------------


async def test_document_text_round_trips(store: ExtractionCandidateStore) -> None:
    document_id = new_id()
    await store.store_document_text(document_id, "Dana called at noon.", ANALYST)

    assert await store.get_document_text(document_id, ANALYST) == "Dana called at noon."


async def test_storing_document_text_twice_upserts_rather_than_conflicts(
    store: ExtractionCandidateStore,
) -> None:
    """A re-run of extraction against the same `document_id` (a different profile, a second
    model) must not fail on a primary-key conflict a caller has no reason to expect from what
    looks like an idempotent action."""
    document_id = new_id()
    await store.store_document_text(document_id, "first version", ANALYST)

    await store.store_document_text(document_id, "second version", ANALYST)

    assert await store.get_document_text(document_id, ANALYST) == "second version"


async def test_get_document_text_denies_a_principal_in_a_different_org_unit(
    store: ExtractionCandidateStore,
) -> None:
    """`CLAUDE.md` rule 4: every read path gets its own access-control test."""
    document_id = new_id()
    await store.store_document_text(document_id, "Dana called at noon.", ANALYST)

    with pytest.raises(DocumentNotFoundError):
        await store.get_document_text(document_id, OTHER_UNIT_ANALYST)


async def test_get_document_text_raises_for_an_unknown_id(store: ExtractionCandidateStore) -> None:
    with pytest.raises(DocumentNotFoundError):
        await store.get_document_text("no-such-document", ANALYST)
