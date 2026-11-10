"""ADR-148 decision 10 at the two uploads that carry their own marking (L1.10): a document added
straight to a case, and an entity's picture. One marked above the deployment's highest is refused
before its body is read or anything is stored, in words that say the limit and never the file's
name or content; one at the ceiling is stored as before."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_document_content,
    get_entity_pictures,
    get_investigations,
    get_principal,
    get_valkey,
)

from schemas.domain import Principal

from .test_document_upload_route import _Content
from .test_entity_picture_routes import _Audit, _Pictures, _Valkey
from .test_link_events import _Cases

#: Cleared above the ceiling, so a refusal is the deployment's limit, not the uploader's clearance.
UPLOADER = Principal(id="analyst-1", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
DOCUMENTS = "/v1/investigations/inv-1/documents"
PICTURE = "/v1/investigations/inv-1/nodes/car-1/picture"
NAME = "SYN-CEILING-FILE.png"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL-SENSITIVE")
    content, pictures = _Content(), _Pictures()
    app.dependency_overrides[get_principal] = lambda: UPLOADER
    app.dependency_overrides[get_document_content] = lambda: content
    app.dependency_overrides[get_entity_pictures] = lambda: pictures
    app.dependency_overrides[get_audit] = lambda: _Audit()
    app.dependency_overrides[get_investigations] = lambda: _Cases({"inv-1"})
    app.dependency_overrides[get_valkey] = lambda: _Valkey()
    test_client = TestClient(app)
    test_client.content = content  # type: ignore[attr-defined]
    test_client.pictures = pictures  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def _params(classification: str) -> dict[str, str]:
    return {"name": NAME, "classification": classification, "legal_basis": "Consent"}


def test_a_document_above_the_ceiling_is_refused_before_anything_is_stored(client: Any) -> None:
    response = client.post(DOCUMENTS, params=_params("SECRET"), content=b"\x89PNG")
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "above_the_deployments_highest_marking"
    assert "OFFICIAL-SENSITIVE" in str(body) and NAME not in str(body)
    assert client.content.calls == []


def test_a_document_at_the_ceiling_is_stored(client: Any) -> None:
    response = client.post(DOCUMENTS, params=_params("OFFICIAL-SENSITIVE"), content=b"\x89PNG")
    assert response.status_code == 200, response.text
    assert len(client.content.calls) == 1


def test_a_picture_above_the_ceiling_is_refused_before_anything_is_stored(client: Any) -> None:
    response = client.put(PICTURE, params=_params("SECRET"), content=b"\x89PNG")
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "above_the_deployments_highest_marking"
    assert NAME not in response.text
    assert client.pictures.calls == []


def test_a_picture_at_the_ceiling_is_stored(client: Any) -> None:
    response = client.put(PICTURE, params=_params("OFFICIAL-SENSITIVE"), content=b"\x89PNG")
    assert response.status_code == 200, response.text
    assert len(client.pictures.calls) == 1
