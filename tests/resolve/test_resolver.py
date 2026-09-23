"""`services/resolve/resolver.py` — `docs/01_DOMAIN_MODEL.md` §4, `docs/06_DECISIONS.md` ADR-021.

No live infra: Splink on DuckDB is entirely in-process, so this runs the real library against the
real ontology's `Person.resolution` config (`packages/ontology/default.yaml`) — the same
discipline `tests/conformance/*` uses a real backing engine for, just one that happens to need no
container here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.resolve.resolver import resolve_entity_type

from ontology.loader import load_default_ontology
from schemas.domain import (
    AuditStub,
    EntityTypeDef,
    Handling,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PERSON_TYPE: EntityTypeDef = next(
    e for e in load_default_ontology().entity_types if e.name == "Person"
)


def _person(node_id: str, family_name: str, given_names: str, date_of_birth: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": date_of_birth,
        },
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )


def _matching_pair() -> list[Node]:
    return [
        _person("n1", "Mercer", "Dana", "1980-01-01"),
        _person("n2", "Mercer", "Dana", "1980-01-01"),
    ]


def test_no_resolution_config_returns_no_candidates() -> None:
    device_type = EntityTypeDef(
        name="Device", pole_class="object", channel="plum", shape="square"
    )
    assert resolve_entity_type(_matching_pair(), device_type) == []


def test_fewer_than_two_nodes_returns_no_candidates() -> None:
    nodes = [_person("n1", "Mercer", "Dana", "1980-01-01")]
    assert resolve_entity_type(nodes, PERSON_TYPE) == []


def test_identical_persons_score_highly_and_share_no_extras() -> None:
    nodes = [
        _person("n1", "Mercer", "Dana", "1980-01-01"),
        _person("n2", "Mercer", "Dana", "1980-01-01"),
        _person("n3", "Okafor", "Susan", "1975-03-03"),
    ]
    candidates = resolve_entity_type(nodes, PERSON_TYPE)
    pairs = {frozenset((c.node_a, c.node_b)) for c in candidates}
    assert frozenset({"n1", "n2"}) in pairs
    assert not any({"n3"} <= pair for pair in pairs)  # n3 shares no soundex/year block with n1/n2


def test_candidate_score_is_a_probability() -> None:
    candidates = resolve_entity_type(_matching_pair(), PERSON_TYPE)
    assert len(candidates) == 1
    assert 0.0 <= candidates[0].score <= 1.0


def test_comparison_vector_carries_one_gamma_per_declared_comparison() -> None:
    candidates = resolve_entity_type(_matching_pair(), PERSON_TYPE)
    vector = candidates[0].comparison_vector
    assert "gamma_family_name" in vector
    assert "gamma_given_names" in vector
    assert "gamma_date_of_birth" in vector
    assert "match_weight" in vector


@pytest.mark.parametrize("_run", range(3))
def test_a_soundex_variant_still_blocks_together(_run: int) -> None:
    """Run three times, not once — `06_DECISIONS.md` ADR-020/021's own lesson from Stage 1-3:
    confirm this is stable across repeated runs before trusting it, the same discipline the
    witness-statement and golden-set flakiness both taught the hard way. Splink/DuckDB here has
    no live model sampling in it, so this is expected to be fully deterministic — the repetition
    is what proves that, not merely assumes it."""
    nodes = [
        _person("n1", "Mercer", "Dana", "1980-01-01"),
        _person("n2", "Marcer", "Dana", "1980-01-01"),
    ]
    candidates = resolve_entity_type(nodes, PERSON_TYPE)
    assert len(candidates) == 1  # soundex(Mercer) == soundex(Marcer): blocked together
    assert candidates[0].score > 0.0


def test_a_hyphenated_family_name_does_not_crash_the_entire_resolution_pass() -> None:
    """A disclosed carry-over, proven through the real reachable path, not
    only against `_soundex` in isolation: before the fix, `resolve_entity_type` raised `IndexError`
    for the *entire population* the moment any one `Person` in it had a hyphenated family name —
    `Smith-Jones` is ordinary UK data, not a constructed edge case. A third, unrelated node is
    included so this also proves the crash's own blast radius: with the fix, an unrelated `Person`
    resolves normally in the same pass as the hyphenated one, not merely alone."""
    nodes = [
        _person("n1", "Smith-Jones", "Dana", "1980-01-01"),
        _person("n2", "Smith-Jones", "Dana", "1980-01-01"),
        _person("n3", "Okafor", "Susan", "1975-03-03"),
    ]
    candidates = resolve_entity_type(nodes, PERSON_TYPE)  # must not raise
    pairs = {frozenset((c.node_a, c.node_b)) for c in candidates}
    assert frozenset({"n1", "n2"}) in pairs
    assert not any({"n3"} <= pair for pair in pairs)
