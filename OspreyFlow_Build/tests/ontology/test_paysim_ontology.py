"""ADR-055 point 2, ruled by the owner on 29 September 2026: an account is an `Endpoint`, and
`TRANSACTED` carries the amount and the kind of transaction (ontology version 10)."""

from __future__ import annotations

from ontology.loader import load_default_ontology

_TRANSACTION_TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}


def test_the_ontology_is_at_version_ten() -> None:
    assert load_default_ontology().version == 10


def test_an_account_is_an_endpoint_kind() -> None:
    ontology = load_default_ontology()
    endpoint = next(e for e in ontology.entity_types if e.name == "Endpoint")
    kind = next(p for p in endpoint.properties if p.name == "endpoint_kind")

    assert "account" in (kind.values or [])
    # The kinds that were there are untouched.
    assert {"msisdn", "imsi", "email", "handle", "iban", "card"} <= set(kind.values or [])


def test_a_transaction_edge_carries_its_amount_and_its_type() -> None:
    ontology = load_default_ontology()
    edge = next(e for e in ontology.edge_types if e.name == "TRANSACTED")
    by_name = {p.name: p for p in edge.properties}

    assert by_name["amount"].type == "float"
    assert by_name["transaction_type"].type == "enum"
    assert set(by_name["transaction_type"].values or []) == _TRANSACTION_TYPES
