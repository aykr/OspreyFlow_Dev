"""The picture routes (ADR-105): what the routes themselves own. A marking and a legal basis are
required, an SVG is refused before anything is kept, a picture over the limit is refused, no picture
and a hidden one answer as one 404, and the reads answer what the service found. The rules behind
them, against a real ArcadeDB, are `test_entity_pictures.py`'s."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_entity_pictures,
    get_investigations,
    get_principal,
    get_valkey,
)
from services.api.entity_pictures import EntityPicture, PictureNotFoundError, PictureSetResult
from services.api.working_set.models import DeltaAdd
from services.extract.writer import NodeNotFoundError

from schemas.domain import Principal

from .test_link_events import _Cases

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
URL = "/v1/investigations/inv-1/nodes/car-1/picture"
PARAMS = {"name": "car.png", "classification": "OFFICIAL", "legal_basis": "Seized under PACE s19"}


class _Pictures:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_: Exception | None = None

    def _maybe_raise(self) -> None:
        if self.raise_:
            raise self.raise_

    async def set(
        self, investigation_id: str, node_id: str, principal: Principal, **kw: Any
    ) -> Any:
        self._maybe_raise()
        self.calls.append({"node_id": node_id, **kw})
        return PictureSetResult(
            document_id="content:1", deltas=[DeltaAdd(seq=1, nodes=[], edges=[])]
        )

    async def pictures(
        self, investigation_id: str, node_ids: list[str], principal: Principal
    ) -> Any:
        self._maybe_raise()
        return [EntityPicture(node_id=n, document_id="content:1") for n in node_ids if n == "car-1"]

    async def remove(self, investigation_id: str, node_id: str, principal: Principal) -> Any:
        self._maybe_raise()
        raise AssertionError("not reached in these cases")

    async def file(self, investigation_id: str, node_id: str, principal: Principal) -> Any:
        self._maybe_raise()
        return b"\x89PNG", "image/png"


class _Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


class _Valkey:
    async def publish(self, channel: str, message: str) -> int:
        return 1


@pytest.fixture
def client() -> Any:
    pictures, audit = _Pictures(), _Audit()
    app.dependency_overrides[get_principal] = lambda: ANALYST
    app.dependency_overrides[get_entity_pictures] = lambda: pictures
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: _Cases({"inv-1"})
    app.dependency_overrides[get_valkey] = lambda: _Valkey()
    test_client = TestClient(app)
    test_client.pictures = pictures  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def test_the_choices_and_the_legal_basis_reach_the_service(client: Any) -> None:
    """The service now writes the `set_entity_picture` audit entry itself (ADR-127 Amendment 23;
    `test_entity_picture_seed.py` proves the entry on both paths), so the route's part is to pass
    the legal basis on and to write no second entry of its own."""
    response = client.put(URL, params=PARAMS, content=b"\x89PNG")
    assert response.status_code == 200, response.text
    (call,) = client.pictures.calls
    assert (call["node_id"], call["name"], call["data"]) == ("car-1", "car.png", b"\x89PNG")
    assert call["handling"].classification == "OFFICIAL"
    assert call["legal_basis"] == "Seized under PACE s19"
    assert client.audit.rows == []


@pytest.mark.parametrize("missing", ["classification", "legal_basis", "name"])
def test_a_marking_a_legal_basis_and_a_name_are_required(client: Any, missing: str) -> None:
    params = dict(PARAMS)
    params.pop(missing)
    assert client.put(URL, params=params, content=b"x").status_code == 422
    assert client.pictures.calls == []


def test_an_svg_is_refused_before_anything_is_kept(client: Any) -> None:
    response = client.put(URL, params={**PARAMS, "name": "car.svg"}, content=b"<svg/>")
    assert response.status_code == 415
    assert client.pictures.calls == []


def test_a_picture_over_the_limit_is_refused(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app as app_module

    monkeypatch.setattr(app_module, "max_upload_bytes", lambda: 4)
    assert client.put(URL, params=PARAMS, content=b"12345").status_code == 413
    assert client.pictures.calls == []


def test_no_picture_and_a_hidden_one_answer_alike(client: Any) -> None:
    client.pictures.raise_ = PictureNotFoundError("car-1")
    for response in (client.get(URL), client.delete(URL)):
        assert (response.status_code, response.json()) == (404, {"error": "picture_not_found"})


def test_an_entity_not_in_the_case_is_not_found(client: Any) -> None:
    client.pictures.raise_ = NodeNotFoundError("car-1")
    response = client.put(URL, params=PARAMS, content=b"\x89PNG")
    assert (response.status_code, response.json()) == (404, {"error": "node_not_found"})


def test_the_reads_answer_what_the_service_found(client: Any) -> None:
    found = client.post("/v1/investigations/inv-1/pictures", json={"node_ids": ["car-1", "car-2"]})
    assert found.json() == [{"node_id": "car-1", "document_id": "content:1"}]
    file = client.get(URL)
    assert (file.status_code, file.content, file.headers["content-type"]) == (
        200,
        b"\x89PNG",
        "image/png",
    )


def test_a_case_the_analyst_may_not_see_answers_as_missing(client: Any) -> None:
    app.dependency_overrides[get_investigations] = lambda: _Cases(set())
    assert (
        client.post("/v1/investigations/inv-1/pictures", json={"node_ids": []}).status_code == 404
    )
    assert client.get(URL).status_code == 404
