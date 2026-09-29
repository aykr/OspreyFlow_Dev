"""Hand-labelled resolution-accuracy check — the resolution-quality equivalent of the golden set
(`tests/golden/harness.py`) for `services/resolve/resolver.py`, following the same fixture
discipline `packages/demo_fixtures/cdr.py` established: deliberately encode known
alias/variation patterns as a synthetic, hand-labelled set and confirm the system lands on the
correct side of a threshold, rather than trusting the mechanism runs without checking whether it
runs *correctly*.

This is the direct evidence behind `06_DECISIONS.md` ADR-021's no-EM-training addendum: Splink's
untrained `comparison_library` defaults are only a safe choice if they actually discriminate real
duplicate/non-duplicate pairs on this ontology's configured comparisons
(`exact`/`jaro_winkler` over `family_name`/`given_names`, `year` blocking on `date_of_birth`).
Two real defects were found writing this check, both now fixed in `resolver.py`, not just
asserted around:

- DuckDB's `jaro_winkler_similarity` is case-sensitive (`'MERCER'` vs `'Mercer'` scored `0.44`,
  not `1.0`) — fixed by casefolding `PropertyType.STRING` values before handing them to Splink.
- The DataFrame builder only pulled `comparison_columns()`, missing any column a blocking rule
  alone references — fixed by unioning blocking and comparison columns.

`DEFAULT_THRESHOLD` (`services/resolve/projection.py`, `0.95`) is deliberately *not* the bar this
file checks against: that threshold governs the query-time `SAME_AS` projection once trained or
tuned, whereas this file is asking a narrower question — do the untrained defaults discriminate
at all, on the right side of a permissive 0.5 split. A pair correctly landing at, say, 0.77 is a
real pass for that question even though 0.77 would not survive the default projection threshold.
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

#: Permissive on purpose — this file checks discrimination direction, not calibration against the
#: real projection threshold (`services/resolve/projection.py`'s `DEFAULT_THRESHOLD` is `0.95`).
DECISION_THRESHOLD = 0.5


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


#: Each entry: (node_a, node_b, expected_match, description). One deliberate alias/variation
#: pattern per row, the same "four renderings of one number" idea `cdr.py` applies to phone
#: numbers, applied here to names — plus the negative controls a discrimination check needs.
CASES: list[tuple[Node, Node, bool, str]] = [
    (
        _person("id-1", "Mercer", "Dana", "1980-01-01"),
        _person("id-2", "Mercer", "Dana", "1980-01-01"),
        True,
        "identical rendering",
    ),
    (
        _person("case-1", "MERCER", "D", "1980-01-01"),
        _person("case-2", "Mercer", "Dana", "1980-01-01"),
        True,
        "upper-case surname + abbreviated given name, same DOB",
    ),
    (
        _person("typo-1", "Marcer", "Dana", "1980-01-01"),
        _person("typo-2", "Mercer", "Dana", "1980-01-01"),
        True,
        "misspelled surname, same soundex code",
    ),
    (
        _person("given-typo-1", "Price", "Callum", "1990-05-05"),
        _person("given-typo-2", "Price", "Calum", "1990-05-05"),
        True,
        "given-name typo, jaro_winkler-close",
    ),
    (
        _person("neg-surname-1", "Mercer", "Dana", "1980-01-01"),
        _person("neg-surname-2", "Mercer", "Susan", "1965-07-07"),
        False,
        "shared surname, different person and DOB",
    ),
    (
        _person("neg-year-1", "Okafor", "Susan", "1980-01-01"),
        _person("neg-year-2", "Mercer", "Dana", "1980-01-01"),
        False,
        "shared DOB year only, unrelated person — user's 'Dana MERCER' vs 'Callum PRICE' case",
    ),
]


def _score_for(node_a: Node, node_b: Node) -> float | None:
    candidates = resolve_entity_type([node_a, node_b], PERSON_TYPE)
    pair = frozenset({node_a.id, node_b.id})
    for candidate in candidates:
        if frozenset({candidate.node_a, candidate.node_b}) == pair:
            return candidate.score
    return None


@pytest.mark.parametrize(
    ("node_a", "node_b", "expected_match", "description"),
    CASES,
    ids=[case[3] for case in CASES],
)
def test_hand_labelled_pair_lands_on_the_correct_side_of_the_threshold(
    node_a: Node, node_b: Node, expected_match: bool, description: str
) -> None:
    score = _score_for(node_a, node_b)
    predicted_match = score is not None and score >= DECISION_THRESHOLD
    assert predicted_match == expected_match, (
        f"{description}: expected match={expected_match}, got score={score}"
    )
