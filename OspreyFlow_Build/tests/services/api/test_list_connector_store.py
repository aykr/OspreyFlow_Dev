"""The screening-list connector's Postgres store, live under a lease (`06_DECISIONS.md` ADR-140
Amendment 13; rule 14): it refuses what its in-memory twin refuses, so the route tests that run on
the twin are tests of the real thing (rule 15).

What a mistake would do, and the case that catches it:
- two deployment lists of one name, which a dataset's Lookup could not tell apart —
  `test_the_postgres_store_refuses_what_the_twin_refuses` (each store in turn);
- a version applied over a version it did not start from, so two imports at once both "win";
- a subscription to a list that does not exist, or a slot run twice by two replicas;
- an import's record, or a list's failure, not read back as written —
  `test_imports_and_failures_are_read_back`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.list_connector import (
    InMemoryListStore,
    ListConnectorRefused,
    ListNotFound,
    PostgresListStore,
)

from schemas.list_connector import BlankListMapping, DeploymentListInput, ListImport
from schemas.monitoring import ListSchedule

AT = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


@pytest.fixture
async def postgres() -> AsyncIterator[PostgresListStore]:
    dsn = PostgresConfig.from_env().dsn
    made = await PostgresListStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    await conn.execute("DELETE FROM deployment_lists WHERE name LIKE 'Store test%'")
    await conn.close()
    yield made
    await made.close()


def _body(name: str = "Store test list") -> DeploymentListInput:
    return DeploymentListInput(
        name=name, template="blank", location="client.csv",
        mapping=BlankListMapping(ref="id", primary_name="name"),
    )  # fmt: skip


async def _refusals(store: object) -> None:
    store_: PostgresListStore = store  # type: ignore[assignment]
    made = await store_.add(_body(), "admin-1")
    with pytest.raises(ListConnectorRefused):
        await store_.add(_body(), "admin-2")
    assert await store_.apply_version(made.id, previous=0, version=1, digest="d1", entries=2, at=AT)
    assert not await store_.apply_version(
        made.id, previous=0, version=1, digest="d2", entries=3, at=AT
    )
    held = await store_.held(made.id)
    assert (held.record.version, held.record.entries, held.digest) == (1, 2, "d1")
    with pytest.raises(ListNotFound):
        await store_.subscribe("ds-a", "no-such-list", "author-1")
    with pytest.raises(ListNotFound):
        await store_.get("no-such-list")
    await store_.subscribe("ds-a", made.id, "author-1")
    await store_.subscribe("ds-a", made.id, "author-1")
    assert await store_.subscribed("ds-a") == [made.id]
    assert await store_.subscribed("ds-b") == []
    await store_.set_schedule(made.id, ListSchedule(every="daily", hour=5), "admin-1", AT)
    assert await store_.mark_slot(made.id, AT)
    assert not await store_.mark_slot(made.id, AT)
    scheduled = [s for s in await store_.scheduled() if s.list_id == made.id]
    assert [(s.owner, s.last_slot) for s in scheduled] == [("admin-1", AT)]
    await store_.unsubscribe("ds-a", made.id)
    assert await store_.subscribed("ds-a") == []


@pytest.mark.parametrize("which", ["twin", "postgres"])
async def test_the_postgres_store_refuses_what_the_twin_refuses(
    which: str, postgres: PostgresListStore
) -> None:
    await _refusals(InMemoryListStore() if which == "twin" else postgres)


async def test_imports_and_failures_are_read_back(postgres: PostgresListStore) -> None:
    made = await postgres.add(_body("Store test imports"), "admin-1")
    failed = ListImport(list_id=made.id, outcome="refused", words="not synthetic (rule 9)")
    await postgres.record_import(failed, at=AT, failure=failed.words)
    assert (await postgres.get(made.id)).failure == failed.words
    ok = ListImport(list_id=made.id, outcome="updated", version=1, added=2, words="version 1")
    await postgres.record_import(ok, at=AT.replace(hour=13), failure=None)
    assert (await postgres.get(made.id)).failure is None
    assert await postgres.imports(made.id) == [ok, failed]
    listed = [r for r in await postgres.lists() if r.id == made.id]
    assert listed[0].mapping == BlankListMapping(ref="id", primary_name="name")
