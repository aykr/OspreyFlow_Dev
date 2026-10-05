"""`POST .../documents` (ADR-094 step 3): what the route itself owns — a marking and a legal basis
are required, an upload over the limit is refused before it is kept, the holder refusal is one 404,
and what the analyst chose reaches the service. The rules behind the upload are
`test_document_content.py`'s."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_document_content,
    get_investigations,
    get_principal,
    get_valkey,
)
from services.api.document_content import HolderNotFoundError, UploadRefusedError
from services.api.working_set.models import DeltaAdd

from schemas.domain import Principal

from .test_link_events import _Cases

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class _Content:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_: Exception | None = None

    async def upload(self, investigation_id: str, principal: Principal, **kwargs: Any) -> Any:
        if self.raise_:
            raise self.raise_
        self.calls.append({"investigation_id": investigation_id, **kwargs})
        from services.api.document_content import DocumentUploadResult

        return DocumentUploadResult(
            document_id="content:1", delta=DeltaAdd(seq=1, nodes=[], edges=[])
        )


class _Audit:
    async def record(self, **kwargs: object) -> None:
        return None


class _Valkey:
    async def publish(self, channel: str, message: str) -> int:
        return 1


@pytest.fixture
def client() -> Any:
    content = _Content()
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_document_content] = lambda: content
    app.dependency_overrides[get_audit] = lambda: _Audit()
    app.dependency_overrides[get_investigations] = lambda: _Cases({"inv-1"})
    app.dependency_overrides[get_valkey] = lambda: _Valkey()
    test_client = TestClient(app)
    test_client.content = content  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


URL = "/v1/investigations/inv-1/documents"


def test_the_choices_reach_the_service(client: Any) -> None:
    response = client.post(
        URL,
        params={
            "name": "IMG_1.png",
            "classification": "OFFICIAL",
            "legal_basis": "Consent",
            "holder": "phone-1",
        },
        content=b"\x89PNG",
    )
    assert response.status_code == 200, response.text
    (call,) = client.content.calls
    assert (call["name"], call["data"], call["holder_id"]) == ("IMG_1.png", b"\x89PNG", "phone-1")
    assert call["handling"].classification == "OFFICIAL"
    assert call["handling"].owning_unit == "unit-1"


@pytest.mark.parametrize("missing", ["classification", "legal_basis", "name"])
def test_a_marking_a_legal_basis_and_a_name_are_required(client: Any, missing: str) -> None:
    params = {"name": "a.png", "classification": "OFFICIAL", "legal_basis": "Consent"}
    params.pop(missing)
    assert client.post(URL, params=params, content=b"x").status_code == 422
    assert client.content.calls == []


def test_an_upload_over_the_limit_is_refused_and_not_kept(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import services.api.app as app_module

    monkeypatch.setattr(app_module, "max_upload_bytes", lambda: 4)
    response = client.post(
        URL,
        params={"name": "a.png", "classification": "OFFICIAL", "legal_basis": "Consent"},
        content=b"12345",
    )
    assert response.status_code == 413
    assert client.content.calls == []


def test_a_holder_not_visible_is_one_404(client: Any) -> None:
    client.content.raise_ = HolderNotFoundError("phone-9")
    response = client.post(
        URL,
        params={
            "name": "a.png",
            "classification": "OFFICIAL",
            "legal_basis": "Consent",
            "holder": "phone-9",
        },
        content=b"x",
    )
    assert (response.status_code, response.json()) == (404, {"error": "holder_not_found"})


def test_a_refused_upload_says_why(client: Any) -> None:
    # A name the upload's own name check passes; the refusal here is the service's.
    client.content.raise_ = UploadRefusedError(
        "the marking SECRET is one you could not read yourself"
    )
    response = client.post(
        URL,
        params={"name": "a.png", "classification": "SECRET", "legal_basis": "Consent"},
        content=b"x",
    )
    assert response.status_code == 422
    assert "SECRET" in response.json()["detail"]


@pytest.mark.parametrize("name", ["clip.mov", "clip.webm", "photo.webp", "anim.gif"])
def test_every_kind_the_reader_shows_passes_the_name_check(client: Any, name: str) -> None:
    """The route's name check takes the content kinds, not the studio's tabular-source list, which
    has no `.mov`, `.webm`, `.webp` or `.gif`."""
    response = client.post(
        URL, params={"name": name, "classification": "OFFICIAL", "legal_basis": "Consent"}, content=b"x"
    )
    assert response.status_code == 200, response.text
