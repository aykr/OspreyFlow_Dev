"""A classification left blank on Connect is recorded as PUBLIC (owner ruling, 3 October 2026:
"the classification needs to include public and also it does not need to be mandatory"; spec 09 §2
amended by ADR-068). The Glass says so beside the box; the server makes it true, so a draft never
carries an empty marking whatever client wrote it.

PUBLIC is the lowest level of the UK scheme, so a blank marking can never be *more* restrictive than
the owner's ruling says, and an OFFICIAL reader still sees it."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_principal,
    get_studio_recipes,
)

from ontology.handling import HandlingScheme, load_uk_le_scheme
from tests.services.api.any_case import AnyCase
from tests.services.api.test_app import _FakeAudit
from tests.services.api.test_studio_recipe_routes import SOURCE_AUTHOR, _FakeStudioRecipes

#: ADR-099 Amendment 3: the Studio's routes are the case's.
CASE = "/v1/investigations/inv-1"


def test_public_is_the_lowest_level_of_the_uk_scheme() -> None:
    scheme = load_uk_le_scheme()
    assert scheme.classification[0] == "PUBLIC"
    assert scheme.classification[1:] == ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"]


def test_an_official_reader_clears_public_and_a_public_reader_does_not_clear_official() -> None:
    scheme = load_uk_le_scheme()
    assert scheme.clears("OFFICIAL", "PUBLIC") is True
    assert scheme.clears("PUBLIC", "PUBLIC") is True
    assert scheme.clears("PUBLIC", "OFFICIAL") is False


@pytest.fixture
def client_and_store() -> Iterator[tuple[TestClient, _FakeStudioRecipes]]:
    store = _FakeStudioRecipes()
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    app.dependency_overrides[get_studio_recipes] = lambda: store
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    try:
        yield TestClient(app), store
    finally:
        for dep in (get_principal, get_audit, get_studio_recipes, get_handling_scheme):
            app.dependency_overrides.pop(dep, None)


def _body(handling: dict[str, str]) -> dict[str, object]:
    return {"label": "Carrier A", "connector_profile": "generic-csv", "handling": handling}


def test_create_with_nothing_marked_records_public(
    client_and_store: tuple[TestClient, _FakeStudioRecipes],
) -> None:
    client, store = client_and_store
    assert client.post(f"{CASE}/ingest/recipes", json=_body({})).status_code == 201
    assert store.create_calls[-1]["handling"] == {"classification": "PUBLIC"}


def test_create_keeps_the_other_marking_fields_and_adds_public(
    client_and_store: tuple[TestClient, _FakeStudioRecipes],
) -> None:
    client, store = client_and_store
    handling = {"handling_code": "P", "originator": "unit-1", "owning_unit": "unit-1"}
    assert client.post(f"{CASE}/ingest/recipes", json=_body(handling)).status_code == 201
    assert store.create_calls[-1]["handling"] == {**handling, "classification": "PUBLIC"}


@pytest.mark.parametrize("blank", ["", "   "])
def test_an_empty_or_blank_classification_counts_as_left_blank(
    client_and_store: tuple[TestClient, _FakeStudioRecipes], blank: str
) -> None:
    client, store = client_and_store
    client.post(f"{CASE}/ingest/recipes", json=_body({"classification": blank}))
    assert store.create_calls[-1]["handling"] == {"classification": "PUBLIC"}


def test_a_classification_the_analyst_chose_is_never_replaced(
    client_and_store: tuple[TestClient, _FakeStudioRecipes],
) -> None:
    client, store = client_and_store
    client.post(f"{CASE}/ingest/recipes", json=_body({"classification": "SECRET"}))
    assert store.create_calls[-1]["handling"] == {"classification": "SECRET"}


def test_editing_a_draft_also_fills_a_blank_classification(
    client_and_store: tuple[TestClient, _FakeStudioRecipes],
) -> None:
    client, store = client_and_store
    created = client.post(f"{CASE}/ingest/recipes", json=_body({"classification": "SECRET"})).json()
    response = client.patch(f"{CASE}/ingest/recipes/{created['recipe_id']}", json=_body({}))
    assert response.status_code == 200, response.text
    assert store.update_calls[-1]["handling"] == {"classification": "PUBLIC"}


def test_a_draft_with_every_other_answer_and_no_classification_is_ready_for_profile(
    client_and_store: tuple[TestClient, _FakeStudioRecipes],
) -> None:
    client, _store = client_and_store
    response = client.post(
        f"{CASE}/ingest/recipes",
        json={
            "label": "Carrier A",
            "connector_profile": "generic-csv",
            "source_location": "/var/lib/osprey/ingest/uploaded/carrier.csv",
            "handling": {"handling_code": "P", "originator": "unit-1", "owning_unit": "unit-1"},
            "legal_basis": "RIPA s22",
        },
    )
    assert response.json()["ready_for_profile"] is True


def test_a_scheme_without_public_falls_back_to_its_lowest_level(
    client_and_store: tuple[TestClient, _FakeStudioRecipes],
) -> None:
    """The US scheme has no PUBLIC; "blank means the lowest level" is what the ruling becomes
    there, rather than a marking the scheme cannot express."""
    client, store = client_and_store
    app.dependency_overrides[get_handling_scheme] = lambda: HandlingScheme(
        name="other",
        classification=["UNCLASSIFIED", "RESTRICTED"],
        handling_codes={},
        action_codes={},
        sanitisation_codes={},
    )
    client.post(f"{CASE}/ingest/recipes", json=_body({}))
    assert store.create_calls[-1]["handling"] == {"classification": "UNCLASSIFIED"}
