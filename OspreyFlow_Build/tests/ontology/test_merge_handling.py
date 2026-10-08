"""A repeated write never lowers handling (ADR-102): the merged element keeps the most restrictive
of each part, whichever order the writes came in. Lowering it is an analyst's explicit change.

What a mistake would do, and the case that catches it:

- the later, lower write winning, as it did before (`test_the_higher_classification_is_kept`);
- a restricted code lost to a permitted one (`test_the_more_restrictive_handling_code_is_kept`);
- an action or sanitisation caveat dropped (`test_a_caveat_is_never_dropped`);
- the access check's units taken from the newcomer (`test_the_units_are_the_existing_ones`);
- a code the scheme does not define ranked by guesswork (`test_an_unknown_code_is_refused`).
"""

from __future__ import annotations

from datetime import date

import pytest

from ontology.errors import HandlingSchemeError
from ontology.handling import load_uk_le_scheme, merge_handling
from schemas.domain import Handling

SCHEME = load_uk_le_scheme()


def _h(classification: str = "OFFICIAL", code: str = "P", **rest: object) -> Handling:
    return Handling(
        classification=classification, handling_code=code, originator="unit-1",
        owning_unit="unit-1", **rest,  # type: ignore[arg-type]
    )


def _both_ways(a: Handling, b: Handling) -> tuple[Handling, Handling]:
    return merge_handling(a, b, SCHEME), merge_handling(b, a, SCHEME)


def test_the_higher_classification_is_kept() -> None:
    for merged in _both_ways(_h("SECRET"), _h("OFFICIAL")):
        assert merged.classification == "SECRET"
    assert merge_handling(_h("OFFICIAL"), _h("OFFICIAL-SENSITIVE"), SCHEME).classification == (
        "OFFICIAL-SENSITIVE"
    )


def test_the_more_restrictive_handling_code_is_kept() -> None:
    for low, high in [("P", "C"), ("P", "R"), ("C", "R")]:
        for merged in _both_ways(_h(code=low), _h(code=high)):
            assert merged.handling_code == high


def test_a_caveat_is_never_dropped() -> None:
    # A1 forbids direct action and needs the originator; A2 permits action; none says nothing.
    for merged in _both_ways(_h(action_code="A1"), _h(action_code="A2")):
        assert merged.action_code == "A1"
    for merged in _both_ways(_h(action_code="A2"), _h()):
        assert merged.action_code == "A2"
    # S2 needs the originator consulted; S1 does not.
    for merged in _both_ways(_h(sanitisation_code="S1"), _h(sanitisation_code="S2")):
        assert merged.sanitisation_code == "S2"
    for merged in _both_ways(_h(sanitisation_code="S1"), _h()):
        assert merged.sanitisation_code == "S1"
    # The earlier review date, and a legal basis kept once given.
    early, late = date(2027, 1, 1), date(2028, 1, 1)
    for merged in _both_ways(_h(review_date=early), _h(review_date=late)):
        assert merged.review_date == early
    assert merge_handling(_h(legal_basis="s.1"), _h(), SCHEME).legal_basis == "s.1"
    assert merge_handling(_h(), _h(legal_basis="s.2"), SCHEME).legal_basis == "s.2"


def test_the_units_are_the_existing_ones() -> None:
    incoming = _h("SECRET", "R").model_copy(
        update={"owning_unit": "unit-2", "originator": "unit-2"}
    )
    merged = merge_handling(_h(), incoming, SCHEME)
    assert (merged.owning_unit, merged.originator) == ("unit-1", "unit-1")
    assert (merged.classification, merged.handling_code) == ("SECRET", "R")


def test_the_same_handling_twice_is_unchanged() -> None:
    same = _h("SECRET", "C", action_code="A1", sanitisation_code="S2")
    assert merge_handling(same, same, SCHEME) == same


def test_an_unknown_code_is_refused() -> None:
    with pytest.raises(HandlingSchemeError):
        merge_handling(_h(), _h(classification="TOP-SECRET-ISH"), SCHEME)
    with pytest.raises(HandlingSchemeError):
        merge_handling(_h(code="Z"), _h(), SCHEME)
