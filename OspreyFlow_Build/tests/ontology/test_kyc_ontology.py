"""Ontology v16 (`06_DECISIONS.md` ADR-109 phase F, the KYC addendum): what onboarding needs the
graph to say. A customer is verified by a Document (`VERIFIED_BY`), whose kind, expiry and fraud
mark the KYC status is computed from; an organisation carries its country and industry (the
baseline risk assessment's inputs); a party matched to a screening list carries the listing; an
IP address is an Endpoint; an organisation, like a person, uses one (shared-attribute checks).
"""

from __future__ import annotations

from ontology.loader import load_default_ontology


def test_v16_carries_what_kyc_reads() -> None:
    core = load_default_ontology()
    assert core.version == 16
    verified_by = core.edge_type("VERIFIED_BY")
    assert verified_by is not None
    assert set(verified_by.from_types) == {"Person", "Organisation"}
    assert verified_by.to_types == ["Document"]
    document = {p.name: p for p in core.entity_type("Document").properties}  # type: ignore[union-attr]
    assert {"document_kind", "expires_on", "fraudulent"} <= set(document)
    assert document["expires_on"].type.value == "date"
    organisation = {p.name for p in core.entity_type("Organisation").properties}  # type: ignore[union-attr]
    assert {"country", "industry", "listing", "list_name"} <= organisation
    person = {p.name for p in core.entity_type("Person").properties}  # type: ignore[union-attr]
    assert {"listing", "list_name"} <= person
    kinds = {p.name: p for p in core.entity_type("Endpoint").properties}["endpoint_kind"]  # type: ignore[union-attr]
    assert "ip" in (kinds.values or [])
    assert "Organisation" in core.edge_type("USES").from_types  # type: ignore[union-attr]
