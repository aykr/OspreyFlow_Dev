"""Domain ontology packs (`06_DECISIONS.md` ADR-108, phase D): versioned, licence-registered
overlays over the POLE core — FIBO (financial), NIEM (crime, roles as role-edges with validity),
STIX 2.1 (cyber) — composed per pipeline, never editing the core.

Rule 12's named tests: a pack entity colliding with the core fails
`test_an_entity_name_collision_is_refused`; an edge silently redefining a core edge fails
`test_an_edge_collision_without_extends_is_refused`; a composed schema that broke the loader's own
channel-and-shape rule fails `test_every_pack_composes_cleanly_over_the_core`.
"""

from __future__ import annotations

import pytest

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from ontology.packs import PACK_NAMES, compose_with_packs


def test_the_pack_names_are_a_closed_set() -> None:
    assert PACK_NAMES == ("fibo", "niem", "stix")


@pytest.mark.parametrize("name", ["fibo", "niem", "stix"])
def test_every_pack_composes_cleanly_over_the_core(name: str) -> None:
    core = load_default_ontology()
    composed = compose_with_packs(core, [name])
    # Nothing of the core is lost or changed in place.
    core_entities = {e.name for e in core.entity_types}
    assert core_entities <= {e.name for e in composed.entity_types}
    assert composed.version == core.version


def test_an_unknown_pack_is_refused_by_name() -> None:
    with pytest.raises(OntologyError):
        compose_with_packs(load_default_ontology(), ["marvel"])


def test_fibo_brings_accounts_and_beneficial_ownership() -> None:
    composed = compose_with_packs(load_default_ontology(), ["fibo"])
    entities = {e.name for e in composed.entity_types}
    edges = {e.name: e for e in composed.edge_types}
    assert "Account" in entities
    assert "BENEFICIAL_OWNER_OF" in edges and edges["BENEFICIAL_OWNER_OF"].directed
    assert "HOLDS_ACCOUNT" in edges
    # The pack extends TRANSACTED's ends to Accounts rather than redefining it.
    assert "Account" in edges["TRANSACTED"].from_types and "Account" in edges["TRANSACTED"].to_types


def test_niem_roles_are_role_edges_with_validity() -> None:
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    edges = {e.name: e for e in composed.edge_types}
    used_as = edges["USED_AS"]
    assert used_as.temporal, "a role holds for a time (ADR-108 ruling Q4)"
    assert any(p.name == "role" and p.required for p in used_as.properties)
    assert "Vehicle" in used_as.from_types and "Event" in used_as.to_types
    assert edges["ROLE_IN"].temporal


def test_stix_brings_sdos_and_sros_and_extends_uses() -> None:
    composed = compose_with_packs(load_default_ontology(), ["stix"])
    entities = {e.name for e in composed.entity_types}
    edges = {e.name: e for e in composed.edge_types}
    assert {"ThreatActor", "Campaign", "Malware", "Vulnerability", "Infrastructure"} <= entities
    assert {"ATTRIBUTED_TO", "TARGETS", "INDICATES", "COMPROMISES"} <= set(edges)
    assert "ThreatActor" in edges["USES"].from_types and "Malware" in edges["USES"].to_types


def test_packs_compose_together_and_the_result_still_loads() -> None:
    composed = compose_with_packs(load_default_ontology(), ["fibo", "niem", "stix"])
    names = [e.name for e in composed.entity_types]
    assert len(names) == len(set(names))


def test_an_entity_name_collision_is_refused() -> None:
    core = load_default_ontology()
    doubled = compose_with_packs(core, ["fibo"])
    with pytest.raises(OntologyError, match="Account"):
        compose_with_packs(doubled, ["fibo"])


def test_an_edge_collision_without_extends_is_refused() -> None:
    core = load_default_ontology()
    once = compose_with_packs(core, ["niem"])
    # NIEM's USED_AS is a definition, not an extension; composing it twice redefines it.
    with pytest.raises(OntologyError, match="USED_AS"):
        compose_with_packs(once, ["niem"])
