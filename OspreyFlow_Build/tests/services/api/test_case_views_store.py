"""`PostgresCaseViewStore` against real Postgres (a lane's leased test stack; ADR-144 decision 3;
`01_DOMAIN_MODEL.md` §2.2c). Each test in a schema of its own.

The visibility the in-memory store proves in `test_case_views.py` is held here by the SQL itself:
every read names its reader in the `WHERE` clause (rule 3), so a private view of someone else is
never retrieved. `test_the_postgres_privacy_check_fails_with_the_reader_planted_out` shows that
clause is what keeps it: with it replaced by `TRUE`, Bob reads Alice's private view.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from services.api import case_views as case_views_module
from services.api.case_views import NotTheViewsCreator, PostgresCaseViewStore, ViewNotFound
from services.api.config import PostgresConfig

from conduit_common.identity import new_id
from schemas.case_views import CaseViewInput

CASE = "case-k"


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"case_views_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


@pytest.fixture
async def store(dsn: str) -> AsyncIterator[PostgresCaseViewStore]:
    held = await PostgresCaseViewStore.connect(dsn)
    yield held
    await held.close()


def _input(**given: object) -> CaseViewInput:
    return CaseViewInput.model_validate(
        {"name": "Contacts", "node_ids": ["n-1", "n-2"], "layout": {"n-1": {"x": 1, "y": 2}}}
        | given
    )


async def test_a_view_round_trips_with_its_lens(store: PostgresCaseViewStore) -> None:
    saved = await store.save(CASE, _input(window={"valid_from": "2026-01-01T00:00:00Z"}), "alice")
    read = await store.get(CASE, saved.id, "alice")
    assert read == saved
    assert read.node_ids == ["n-1", "n-2"] and read.layout["n-1"].x == 1
    assert read.wire().chosen == 2


async def test_a_private_view_is_invisible_to_another_member_on_postgres(
    store: PostgresCaseViewStore,
) -> None:
    saved = await store.save(CASE, _input(), "alice")
    assert await store.visible_in(CASE, "bob") == []
    for act in (store.get, store.share, store.delete):
        with pytest.raises(ViewNotFound):
            await act(CASE, saved.id, "bob")
    with pytest.raises(ViewNotFound):
        await store.get("another-case", saved.id, "alice")

    await store.share(CASE, saved.id, "alice")
    assert [v.id for v in await store.visible_in(CASE, "bob")] == [saved.id]
    assert (await store.get(CASE, saved.id, "bob")).shared
    for act in (store.share, store.delete):
        with pytest.raises(NotTheViewsCreator):
            await act(CASE, saved.id, "bob")
    await store.delete(CASE, saved.id, "alice")
    assert await store.visible_in(CASE, "alice") == []


async def test_the_postgres_privacy_check_fails_with_the_reader_planted_out(
    store: PostgresCaseViewStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the real query: the reader clause replaced by one every row passes (`$2` still
    bound, so the query runs as the real one does)."""
    saved = await store.save(CASE, _input(), "alice")
    monkeypatch.setattr(case_views_module, "_VISIBLE", "($2::text IS NOT NULL)")
    assert [v.id for v in await store.visible_in(CASE, "bob")] == [saved.id]
    assert (await store.get(CASE, saved.id, "bob")).id == saved.id


# --- a view's conversation and its proposals, on Postgres (L3.2's Q2; the review's items 3, 11) --


async def test_the_postgres_question_store_never_mixes_a_views_conversation(dsn: str) -> None:
    from datetime import UTC, datetime

    from services.api.questions import PostgresQuestionStore, QuestionEntry

    store = await PostgresQuestionStore.connect(dsn)
    try:
        for entry_id, view_id in (("q-case", None), ("q-view", "v-1")):
            await store.add(
                QuestionEntry(
                    id=entry_id, investigation_id=CASE, author="alice", question="Who?",
                    answer="Dana.", model="local-model", view_id=view_id,
                    created_at=datetime(2026, 11, 8, tzinfo=UTC),
                )  # fmt: skip
            )
        assert [e.id for e in await store.list_for_case(CASE)] == ["q-case"]
        assert [e.id for e in await store.list_for_case(CASE, "v-1")] == ["q-view"]
        assert await store.list_for_case(CASE, "v-2") == []
    finally:
        await store.close()


async def _a_views_proposal(dsn: str) -> tuple[Any, str]:
    from services.api.review import ExtractionCandidateStore
    from services.extract.candidates import ExtractionCandidate

    from schemas.domain import Handling, Principal

    store = await ExtractionCandidateStore.connect(dsn)
    alice = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1")
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )
    (record,) = await store.store(
        [
            ExtractionCandidate(
                id=new_id(), document_id="doc-1", entity_type="Person",
                properties={"family_name": "MERCER"}, confidence=0.9, model="local-model",
                locator="char span 0-6", excerpt_hash="", handling=handling,
            )  # fmt: skip
        ],
        alice,
        view_id="v-1",
    )
    return store, record.id


async def test_a_views_proposal_is_read_on_postgres_only_through_its_view(dsn: str) -> None:
    from services.api.dataset_scope import read_in_view, set_case_datasets
    from services.api.review import ExtractionCandidateNotFoundError

    from schemas.domain import Principal

    store, candidate = await _a_views_proposal(dsn)
    bob = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1")
    try:
        set_case_datasets(None)
        assert await store.list_for_document("doc-1", bob) == []
        with pytest.raises(ExtractionCandidateNotFoundError):
            await store.get_authorized(candidate, bob)
        read_in_view("v-2")
        assert await store.list_for_document("doc-1", bob) == []
        read_in_view("v-1")
        assert [r.id for r in await store.list_for_document("doc-1", bob)] == [candidate]
        assert (await store.get_authorized(candidate, bob)).view_id == "v-1"
    finally:
        set_case_datasets(None)
        await store.close()


async def test_the_postgres_view_clause_check_fails_with_it_planted_out(
    dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the real query: the clause planted to pass every row, a view's proposal is
    listed with no view opened."""
    from services.api import review
    from services.api.dataset_scope import set_case_datasets

    from schemas.domain import Principal

    monkeypatch.setattr(review, "view_clause", lambda position: ("", []))
    store, candidate = await _a_views_proposal(dsn)
    try:
        set_case_datasets(None)
        bob = Principal(id="bob", clearance="OFFICIAL", org_unit="unit-1")
        assert [r.id for r in await store.list_for_document("doc-1", bob)] == [candidate]
    finally:
        await store.close()
