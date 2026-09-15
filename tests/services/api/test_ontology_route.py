"""`GET /v1/ontology` route wiring — `docs/02_GLASS_FRONTEND.md` §4's
channel/shape mapping, served from the loaded ontology rather than
duplicated client-side. Same style as `test_search_route.py`: fakes behind
`app.dependency_overrides`, proving only the wiring — `ontology/loader.py`'s
own correctness is out of scope here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_ontology, get_principal

from ontology.loader import load_default_ontology
from schemas.domain import Principal

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_ontology] = load_default_ontology
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_returns_entity_types_with_channel_and_shape(client: TestClient) -> None:
    response = client.get("/v1/ontology")

    assert response.status_code == 200
    body = response.json()
    person = next(e for e in body["entity_types"] if e["name"] == "Person")
    assert person["channel"] == "indigo"
    assert person["shape"] == "circle"


def test_requires_authentication(client: TestClient) -> None:
    app.dependency_overrides.pop(get_principal)

    response = client.get("/v1/ontology")

    assert response.status_code in (401, 403)
