"""ADR-130 decision 1 against the real stores: `HotlistStore` (Postgres, owner-checked read),
`AlertStore` and the real ArcadeDB graph. The hermetic cases are in `test_alert_view_explains.py`;
this proves the same through the real owner check and the real access filter.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore
from services.api.watch_routes import alert_to_view

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Alert,
    AlertMode,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

# Ids of this run's own: the stores are shared with other suites, whose rows a fixed id would
# meet (a stranger's "empty" list once held 220 other tests' alerts).
OWNER = Principal(id=f"owner-{new_id()}", clearance="OFFICIAL", org_unit="unit-1")
STRANGER = Principal(id=f"stranger-{new_id()}", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
async def stores():
    dsn = PostgresConfig.from_env().dsn
    alerts = await AlertStore.connect(dsn)
    hotlists = await HotlistStore.connect(dsn)
    yield alerts, hotlists
    await alerts.close()
    await hotlists.close()


def _endpoint(*, owning_unit: str = "unit-1", classification: str = "OFFICIAL") -> NodeWrite:
    now = datetime.now(UTC)
    sources = [
        SourceRef(
            document_id="in/batch/pid_seized_comms_batch2.csv", locator="row 3", excerpt_hash=""
        )
    ]
    sources += [
        SourceRef(document_id="in/batch/pid_pin_calls.csv", locator=f"row {i}", excerpt_hash="")
        for i in (4, 5)
    ]
    return NodeWrite(
        id=new_id(),
        type="Endpoint",
        properties={"value_normalised": "+447700900640", "endpoint_kind": "msisdn"},
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=sources, first_seen=now),
        handling=Handling(
            classification=classification, handling_code="P", originator=owning_unit,
            owning_unit=owning_unit,
        ),
        created_by="test",
        created_at=now,
    )  # fmt: skip


async def test_the_owner_sees_the_hotlist_and_what_fired_it_and_a_stranger_the_hotlist_never(
    stores,
) -> None:
    alerts, hotlists = stores
    hotlist = await hotlists.create(OWNER, identifier="07700 900640", review_date=date(2027, 1, 31))
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as graph:
        tx = await graph.begin_transaction()
        (node_id,) = await graph.upsert_nodes([_endpoint()], tx)
        await graph.commit_transaction(tx)
        alert = Alert(
            id=new_id(), rule_id=f"hotlist:{hotlist.id}", owner_id=OWNER.id, mode=AlertMode.FULL,
            referent_node_ids=[node_id], created_at=datetime.now(UTC),
        )  # fmt: skip
        await alerts.save(alert)

        mine = await alert_to_view(alert, OWNER, graph, hotlists)
        assert mine.hotlist is not None and mine.hotlist.identifier == "07700 900640"
        assert mine.hotlist.review_date == date(2027, 1, 31)
        assert mine.fired_on is not None
        files = [(f.name, f.row, f.rows) for f in mine.fired_on[0].files]
        assert files == [("pid_seized_comms_batch2.csv", 3, None), ("pid_pin_calls.csv", None, 2)]

        # Another analyst's list never holds it (as before), and reading the hotlist as them is
        # refused by the real store, so nothing of it reaches a view built for them.
        assert await alerts.list_authorized(STRANGER) == []
        theirs = await alert_to_view(alert, STRANGER, graph, hotlists)
        assert theirs.hotlist is None

        # Revoke: the node becomes unreadable to the owner; no fired_on, nothing about it.
        tx = await graph.begin_transaction()
        hidden = _endpoint(owning_unit="unit-2", classification="SECRET")
        await graph.supersede_node(node_id, hidden, tx)
        await graph.commit_transaction(tx)
        revoked = await alert_to_view(alert, OWNER, graph, hotlists)
        assert revoked.evidence_available is False and revoked.fired_on is None
        assert "pid_" not in revoked.model_dump_json()
