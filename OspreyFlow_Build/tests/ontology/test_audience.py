"""ADR-102 Amendment 3: a link merges only within one audience. `audience_of` is the key two writes
share exactly when the same principals see both: the classification, the handling code, the set of
datasets (ADR-099) and, only where the code is restricted, the originator and the owning unit (the
access step reads them only then, `access_filter.py`). What a mistake would do:

- a unit left in the key of an unrestricted link, so two units' rows of one pair never merge and a
  count the owner never asked to split is split (`test_units_decide_nothing_for_an_unrestricted_code`);
- a unit left out of the key of a restricted link, so a link restricted to one unit absorbs another's
  row (`test_a_restricted_code_is_decided_by_both_its_units`);
- the datasets compared as a list, so the same two cases listed in another order, or twice, are
  split (`test_the_datasets_are_a_set`)."""

from __future__ import annotations

import pytest

from ontology.handling import audience_of, is_restricted, load_uk_le_scheme
from schemas.domain import Handling

SCHEME = load_uk_le_scheme()


def _handling(**changes: str) -> Handling:
    base = {
        "classification": "OFFICIAL",
        "handling_code": "P",
        "originator": "unit-1",
        "owning_unit": "unit-1",
    }
    return Handling.model_validate({**base, **changes})


def _key(handling: Handling, datasets: list[str] | None = None) -> object:
    return audience_of(handling, datasets or [], SCHEME)


def test_is_restricted_follows_the_schemes_dissemination() -> None:
    assert is_restricted("R", SCHEME) is True
    assert is_restricted("P", SCHEME) is False
    assert is_restricted("C", SCHEME) is False


def test_one_marking_is_one_audience() -> None:
    assert _key(_handling()) == _key(_handling())


@pytest.mark.parametrize("part", ["classification", "handling_code"])
def test_a_different_classification_or_code_is_another_audience(part: str) -> None:
    other = {"classification": "SECRET", "handling_code": "C"}[part]
    assert _key(_handling(**{part: other})) != _key(_handling())


def test_units_decide_nothing_for_an_unrestricted_code() -> None:
    for code in ("P", "C"):
        assert _key(_handling(handling_code=code, owning_unit="unit-2", originator="unit-3")) == _key(
            _handling(handling_code=code)
        )


def test_a_restricted_code_is_decided_by_both_its_units() -> None:
    base = _handling(handling_code="R")
    assert _key(_handling(handling_code="R", owning_unit="unit-2")) != _key(base)
    assert _key(_handling(handling_code="R", originator="unit-2")) != _key(base)
    assert _key(_handling(handling_code="R")) == _key(base)


def test_the_datasets_are_a_set() -> None:
    assert _key(_handling(), ["b", "a"]) == _key(_handling(), ["a", "b", "a"])
    assert _key(_handling(), ["a"]) != _key(_handling(), ["a", "b"])
    assert _key(_handling(), ["a"]) != _key(_handling(), [])


def test_action_and_sanitisation_codes_decide_nothing() -> None:
    """The access step never reads them (`01_DOMAIN_MODEL.md` §2.2), so two writes differing only in
    them are seen by the same principals and merge, as `merge_handling` then keeps the stricter."""
    plain = _handling()
    assert _key(plain) == _key(_handling(action_code="A1"))
    assert _key(plain) == _key(_handling(sanitisation_code="S1"))
