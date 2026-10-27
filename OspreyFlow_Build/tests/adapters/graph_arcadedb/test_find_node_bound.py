"""`find_node(also=...)` past its bound, through the real adapter over a stub client (rule 2, 15).

The kind of an Endpoint is not a stored top-level field, so it cannot be a `has` step (found live
on ArcadeDB, 27 October 2026), and the nodes sharing the value are read to choose among. The read is
`FIND_WITH_ALSO_LIMIT + 1` so that overflowing is knowable: with more than the bound read and none
of the kind among them, the adapter raises `FindLimitExceeded` and never answers `None`, which a
caller reads as "nothing here". The stub honours the query's own `.limit(n)` as the store does, so
an adapter that read only the bound would see exactly the bound and could not tell.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from adapters.graph_arcadedb.adapter import FIND_WITH_ALSO_LIMIT, GraphArcadeDBAdapter
from ontology.handling import load_uk_le_scheme
from ports.graph import FindLimitExceeded
from schemas.domain import Principal

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1")
KIND = {"endpoint_kind": "account"}


def _record(node_id: str, kind: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": "mx_Endpoint",
        "properties": {"value_normalised": "SYN-70417", "endpoint_kind": kind},
        "provenance": {
            "state": "asserted",
            "sources": [{"document_id": "d", "locator": "p.1", "excerpt_hash": "a" * 64}],
            "first_seen": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        },
        "handling": {
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        "audit": {
            "created_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "created_by": "loader",
        },
    }


class _StubClient:
    """Answers a `find_node` query with as many of its records as the query's `.limit(n)` allows."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.queries: list[str] = []

    async def gremlin(self, query: str) -> list[dict[str, Any]]:
        self.queries.append(query)
        match = re.search(r"\.limit\((\d+)\)", query)
        assert match is not None
        return self.records[: int(match.group(1))]


def _adapter(records: list[dict[str, Any]]) -> tuple[GraphArcadeDBAdapter, _StubClient]:
    client = _StubClient(records)
    return GraphArcadeDBAdapter(client, load_uk_le_scheme()), client  # type: ignore[arg-type]


async def _find(adapter: GraphArcadeDBAdapter) -> Any:
    return await adapter.find_node("Endpoint", "value_normalised", "SYN-70417", READER, also=KIND)


def _handles(count: int) -> list[dict[str, Any]]:
    return [_record(f"h{n:03d}", "handle") for n in range(count)]


async def test_more_than_the_bound_read_with_no_node_of_the_kind_raises_the_typed_error() -> None:
    adapter, client = _adapter(_handles(FIND_WITH_ALSO_LIMIT + 20))
    with pytest.raises(FindLimitExceeded) as raised:
        await _find(adapter)
    assert raised.value.bound == FIND_WITH_ALSO_LIMIT
    assert f".limit({FIND_WITH_ALSO_LIMIT + 1})." in client.queries[0]


async def test_exactly_the_bound_with_no_node_of_the_kind_is_a_true_miss() -> None:
    """Everything that shares the value was read and none is of the kind: `None` is the truth."""
    adapter, _ = _adapter(_handles(FIND_WITH_ALSO_LIMIT))
    assert await _find(adapter) is None


async def test_a_node_of_the_kind_among_those_read_is_returned_even_past_the_bound() -> None:
    adapter, _ = _adapter([*_handles(FIND_WITH_ALSO_LIMIT), _record("account", "account")])
    found = await _find(adapter)
    assert found is not None and found.id == "account"


async def test_a_lookup_with_no_also_reads_one_node_and_never_raises() -> None:
    adapter, client = _adapter(_handles(FIND_WITH_ALSO_LIMIT + 20))
    found = await adapter.find_node("Endpoint", "value_normalised", "SYN-70417", READER)
    assert found is not None and found.id == "h000"
    assert ".limit(1)." in client.queries[0]
