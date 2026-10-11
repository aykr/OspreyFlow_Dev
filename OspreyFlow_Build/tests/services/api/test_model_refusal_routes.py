"""ADR-095: when the model cannot answer, the analyst is told why in words, never "500". What a
mistake would do, and the case that catches it: the chosen model still downloading shown as a
server fault (`test_a_model_not_yet_available_is_said_in_words`), or a model that answered badly
shown as the same thing as one that is absent (`test_a_failed_extraction_is_said_apart_from_it`)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from adapters.model_litellm.errors import ExtractionFailedError, ModelUnavailableError
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_document_content,
    get_email_extraction,
    get_investigations,
    get_principal,
    get_valkey,
)

from schemas.domain import Principal

from .test_investigation_access_routes import _Audit
from .test_link_type_routes import _Cases

ALICE = Principal(id="alice", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


class _Refusing:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def extract(self, *args: Any, **kwargs: Any) -> Any:
        raise self.error


@pytest.fixture
def client() -> Iterator[Any]:
    def make(error: Exception) -> TestClient:
        app.dependency_overrides[get_investigations] = lambda: _Cases()
        app.dependency_overrides[get_principal] = lambda: ALICE
        app.dependency_overrides[get_audit] = lambda: _Audit()
        app.dependency_overrides[get_valkey] = lambda: None
        app.dependency_overrides[get_email_extraction] = lambda: _Refusing(error)
        app.dependency_overrides[get_document_content] = lambda: _Refusing(error)
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


EMAIL = "/v1/investigations/inv-1/links/e1/events/ev-1/extract"
DOCUMENT = "/v1/investigations/inv-1/documents/doc-1/extract"


@pytest.mark.parametrize("path", [EMAIL, DOCUMENT])
def test_a_model_not_yet_available_is_said_in_words(client: Any, path: str) -> None:
    answer = client(ModelUnavailableError("model 'qwen2.5:7b-instruct' is not available")).post(
        path, json={}
    )
    assert answer.status_code == 503
    body = answer.json()
    assert body["error"] == "model_unavailable"
    assert "qwen2.5:7b-instruct" in body["detail"] and "download" in body["detail"]


@pytest.mark.parametrize("path", [EMAIL, DOCUMENT])
def test_a_failed_extraction_is_said_apart_from_it(client: Any, path: str) -> None:
    answer = client(ExtractionFailedError("did not conform after 3 attempt(s)")).post(path, json={})
    assert answer.status_code == 502
    assert answer.json()["error"] == "extraction_failed"
