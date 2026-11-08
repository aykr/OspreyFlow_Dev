"""`PostgresCaseViewStore` against real Postgres (a lane's leased test stack; ADR-144 decision 3;
`01_DOMAIN_MODEL.md` §2.2c). Each test in a schema of its own.

The visibility the in-memory store proves in `test_case_views.py` is held here by the SQL itself:
every read names its reader in the `WHERE` clause (rule 3), so a private view of someone else is
never retrieved. `test_the_postgres_privacy_check_fails_with_the_reader_planted_out` shows that
clause is what keeps it: with it replaced by `TRUE`, Bob reads Alice's private view.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

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
