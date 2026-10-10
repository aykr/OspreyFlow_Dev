"""Ontology v15 (`06_DECISIONS.md` ADR-109 ruling 2): an alert is a graph node as well as a queue
row. The `Alert` type and its `ALERTED_ON` link must be in the core (so every deployment's store
carries them) and must reach a pack's types (an alert on a FIBO `Account` is the AML case), while
`ALERTED_ON` stays a system link an analyst is never offered to draw by hand.
"""

from __future__ import annotations

from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology


def test_the_core_carries_alert_and_alerted_on_from_version_15() -> None:
    core = load_default_ontology()
    assert core.version >= 15
    alert = core.entity_type("Alert")
    assert alert is not None
    assert {p.name for p in alert.properties} >= {"rule_id", "typology", "words", "raised_at"}
    alerted_on = core.edge_type("ALERTED_ON")
    assert alerted_on is not None
    assert alerted_on.from_types == ["Alert"]
    assert alerted_on.system is True
    # A rule's finding, not a loaded record: drawn dotted like every derived link (ADR-081).
    assert alerted_on.basis == "probabilistic"


def test_an_alert_reaches_a_packs_account() -> None:
    composed = load_deployment_ontology()
    alerted_on = composed.edge_type("ALERTED_ON")
    assert alerted_on is not None
    assert "*" in alerted_on.to_types or "Account" in alerted_on.to_types
