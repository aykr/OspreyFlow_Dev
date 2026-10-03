"""`LinkChangeStore` against real Postgres (`make dev-up`) — the half `test_link_changes.py`'s
in-memory stand-in cannot prove: that a change round-trips with its old and new values intact and is
found only under its own case and the link it produced."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.link_changes import LinkChange, LinkChangeStore

from conduit_common.identity import new_id


@pytest.fixture
async def store():
    s = await LinkChangeStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


def _change(inv: str, previous: str, produced: str) -> LinkChange:
    return LinkChange(
        id=new_id(),
        investigation_id=inv,
        edge_id=produced,
        previous_edge_id=previous,
        changed_by="analyst-1",
        changed_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        reason="Told so",
        before={"type": "ASSOCIATE_OF", "properties": {}, "interval": None, "occurrences": 3},
        after={
            "type": "FAMILY_OF",
            "properties": {"relation": "cousin"},
            "interval": None,
            "occurrences": 3,
        },
    )


async def test_a_change_round_trips_with_its_old_and_new_values(store) -> None:
    inv, old, new = new_id(), new_id(), new_id()
    await store.add(_change(inv, old, new))
    found = await store.produced(inv, new)
    assert found is not None
    assert found.previous_edge_id == old
    assert found.before["type"] == "ASSOCIATE_OF"
    assert found.after["properties"] == {"relation": "cousin"}
    assert found.changed_at == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


async def test_a_change_is_found_only_under_its_own_case_and_link(store) -> None:
    inv, old, new = new_id(), new_id(), new_id()
    await store.add(_change(inv, old, new))
    assert await store.produced(new_id(), new) is None
    assert await store.produced(inv, old) is None  # the replaced link was not produced by it
    assert await store.produced(inv, new_id()) is None
