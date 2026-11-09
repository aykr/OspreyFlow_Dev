"""The grading command's read of the board registry (`scripts/grading_change.py`'s
`registry_reader`; ADR-143 decision 11, L3.7), against real Postgres (a lane's leased test stack),
in a schema of its own: every case's live drawn nodes and links, and nothing withdrawn, no picture
and no match link, which carry no grade."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from scripts.grading_change import registry_reader
from services.api.board_store import PostgresBoardItemStore, new_item
from services.api.config import PostgresConfig

from conduit_common.identity import new_id


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"grading_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


async def test_the_registry_read_is_every_cases_live_drawn_nodes_and_links(dsn: str) -> None:
    store = await PostgresBoardItemStore.connect(dsn)
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=1)
    try:
        made = {}
        for name, case, kind in (
            ("node-k", "case-k", "node"), ("link-k", "case-k", "link"),
            ("node-b", "case-b", "node"), ("gone", "case-k", "node"),
            ("picture", "case-k", "picture"), ("match", "case-k", "match"),
        ):  # fmt: skip
            item = new_item(
                board_id="board", case_id=case, kind=kind, element_id=f"el-{name}",
                author="alice", dataset_id="layer",
            )  # fmt: skip
            await store.add(item, None)
            made[name] = item.item_id
        await store.withdraw("case-k", [made["gone"]], "alice", datetime.now(UTC))
        found = await registry_reader(pool)()
        assert {i.element_id for i in found} == {"el-node-k", "el-link-k", "el-node-b"}
        assert all(i.withdrawn_at is None for i in found)
    finally:
        await pool.close()
        await store.close()
