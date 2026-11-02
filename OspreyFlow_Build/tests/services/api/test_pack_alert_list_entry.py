"""A screening alert added to a report pack names the list's own entry as the list's (step 9e).

Step 9d found the Ledger's screening alert listing "Sofia Ruiz · Person" twice in the Glass: the
alert cites the customer and the list's own entry for the listed party (`kyc_rules._listed_write`
gives it `listing` and `list_name`), joined by an inferred `SAME_AS`. The Glass now says which is
the list's (`names.ts`'s `concernWords`). The pack's stored alert item (`services/api/packs.py`'s
`alert_item`, ADR-134 decision 1) is a frozen snapshot read long after, outside the Glass, so it
must say so itself, or a published pack reads as one person matched twice.

What a mistake would do, and the case that catches it:
- the list's entry stored by name and type alone, like the customer —
  `test_the_list_entry_is_stored_as_the_lists_and_the_customer_is_not`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ontology.handling import load_uk_le_scheme
from services.api.packs import alert_item

from schemas.domain import (
    Alert,
    AlertExplanation,
    AlertMode,
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

NOW = datetime(2026, 10, 6, tzinfo=UTC)
HANDLING = Handling(classification="OFFICIAL", handling_code="P", owning_unit="u", originator="u")


def _node(node_id: str, node_type: str, **properties: object) -> Node:
    return Node(id=node_id, type=node_type, properties=properties, handling=HANDLING,
                provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW,
                                      sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")]),
                audit=AuditStub(created_at=NOW, created_by="seed"))  # fmt: skip


def test_the_list_entry_is_stored_as_the_lists_and_the_customer_is_not() -> None:
    customer = _node("n-customer", "Person", family_name="Ruiz", given_names="Sofia")
    listed = _node("n-listed", "Person", family_name="Ruiz", given_names="Sofia", listing="sanction",
                   list_name="UK Sanctions List (synthetic)")  # fmt: skip
    own = _node("n-alert", "Alert", rule_id="r-k")
    alert = Alert(id="k1", rule_id="typology:r-k", owner_id="admin", mode=AlertMode.FULL,
                  investigation_id="c1", typology="kyc_screening", created_at=NOW,
                  referent_node_ids=["n-customer", "n-listed"], alert_node_id="n-alert")  # fmt: skip
    explained = AlertExplanation(alert=alert, summary="Sofia Ruiz matches “RUIZ, Sofia”",
                                 nodes=[customer, listed, own], severity="high")  # fmt: skip
    by = Principal(id="ed", clearance="SECRET", org_unit="u", roles=["analyst"])
    item = alert_item(explained, [], by, load_uk_le_scheme())
    assert item.alert is not None
    entities = {e.node_id: e for e in item.alert.entities}
    assert set(entities) == {"n-customer", "n-listed"}
    assert entities["n-listed"].list_entry_on == "UK Sanctions List (synthetic)"
    assert entities["n-customer"].list_entry_on is None
    assert entities["n-listed"].name == entities["n-customer"].name == "Sofia Ruiz"
