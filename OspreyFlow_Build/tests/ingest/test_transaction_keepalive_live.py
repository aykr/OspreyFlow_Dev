"""ADR-127 Amendment 20 against a real ArcadeDB: a transaction left idle for 20 seconds, then
written and committed, succeeds and the write is stored. ArcadeDB 26.10.1 expires an idle HTTP
session after 5 to 10 seconds, so without the keep-alive the same transaction fails with a 404
(`test_without_the_keepalive_the_same_transaction_expires`, the plant built into the suite: rule 15,
so the case is shown to be able to fail, and the limit it guards is shown to be there). Needs the
dev stack's ArcadeDB (`ARCADEDB_HTTP_PORT` for another one); 20 seconds each.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig, ArcadeDBError
from conduit_common.identity import new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

IDLE_SECONDS = 20
READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1")


@asynccontextmanager
async def _adapter(keepalive_seconds: float | None) -> AsyncIterator[GraphArcadeDBAdapter]:
    """As `arcadedb_adapter`, with the client's keep-alive set by the case."""
    database = f"conformance_{int(time.time())}_{uuid.uuid4().hex[:12]}"
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(database),
        **({} if keepalive_seconds is not None else {"keepalive_seconds": None}),
    )
    try:
        await client.create_database_if_absent()
        adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await adapter.apply_schema(load_default_ontology())
        yield adapter
    finally:
        await client.drop_database()
        await client.aclose()


def _person() -> NodeWrite:
    now = now_utc()
    return NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": "Idle"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="live", locator="row 1", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling.model_validate(
            {
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": "unit-1",
                "owning_unit": "unit-1",
            }
        ),
        created_by="loader-1",
        created_at=now,
    )


async def test_a_transaction_idle_for_twenty_seconds_still_commits() -> None:
    import asyncio

    async with _adapter(keepalive_seconds=3.0) as adapter:
        tx = await adapter.begin_transaction()
        await asyncio.sleep(IDLE_SECONDS)
        node = _person()
        await adapter.upsert_nodes([node], tx)
        await adapter.commit_transaction(tx)
        stored = await adapter.get_node(node.id, READER)
        assert stored is not None and stored.properties["family_name"] == "Idle"


async def test_without_the_keepalive_the_same_transaction_expires() -> None:
    import asyncio

    async with _adapter(keepalive_seconds=None) as adapter:
        tx = await adapter.begin_transaction()
        await asyncio.sleep(IDLE_SECONDS)
        with pytest.raises(ArcadeDBError) as raised:
            await adapter.upsert_nodes([_person()], tx)
        assert raised.value.status_code == 404
