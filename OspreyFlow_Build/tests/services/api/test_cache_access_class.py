"""`services.api.cache.principal_class`, the cache's key for who may read a result (`spec/03` §7).

What a mistake would do: two principals who may read different things share a cached result, so
one is served what only the other may see. Handling and unit were in the key from the start;
ADR-099 made the case's datasets an access axis like them, so a principal reading Enron and one
reading Fixture Corp, otherwise identical, must not share an entry (the first case below).
Unlimited background work (`datasets=None`) is a class of its own, distinct from a case reading
nothing (`[]`)."""

from __future__ import annotations

from services.api.cache import principal_class

from schemas.domain import Principal

BASE = Principal(id="a", clearance="OFFICIAL", org_unit="unit-1")


def test_two_cases_reading_different_data_are_different_classes() -> None:
    enron = BASE.model_copy(update={"datasets": ["enron"]})
    fixture = BASE.model_copy(update={"datasets": ["fixture-corp"]})
    assert principal_class(enron) != principal_class(fixture)


def test_the_same_datasets_in_another_order_are_one_class() -> None:
    one = BASE.model_copy(update={"datasets": ["enron", "fixture-corp"]})
    other = BASE.model_copy(update={"datasets": ["fixture-corp", "enron"]})
    assert principal_class(one) == principal_class(other)


def test_unlimited_and_nothing_are_different_classes() -> None:
    unlimited = BASE.model_copy(update={"datasets": None})
    nothing = BASE.model_copy(update={"datasets": []})
    assert principal_class(unlimited) != principal_class(nothing)


def test_the_person_is_not_part_of_the_class() -> None:
    other_person = BASE.model_copy(update={"id": "b", "datasets": ["enron"]})
    assert principal_class(other_person) == principal_class(
        BASE.model_copy(update={"datasets": ["enron"]})
    )
