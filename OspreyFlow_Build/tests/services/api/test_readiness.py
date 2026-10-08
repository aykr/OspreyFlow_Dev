"""Whether the deployment's models are present (`06_DECISIONS.md` ADR-095 decision 1, Amendment 2).

The Conduit asks Ollama's own list (`GET /api/tags`) for the models it serves with, and says ready
only when every one is there. What a mistake would do, and the case that catches it:

- ready while the extraction model is still downloading, which is how a first install's extraction
  failed with nothing saying why (`test_not_ready_until_the_extraction_model_is_present`);
- a model counted present because a different tag of the same name is (`qwen2.5:7b-instruct` is
  not `qwen2.5:14b-instruct`; a bare `name` means `name:latest`)
  (`test_a_model_is_present_only_under_its_own_tag`);
- ready, or an error, when Ollama does not answer: the real server refuses a connection while it
  starts and answers 500 when it is unwell, so the fake does both
  (`test_an_ollama_that_does_not_answer_is_not_ready_and_says_so`);
- the route answering without a principal (`test_the_route_needs_a_principal`).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_principal
from services.api.config import DeploymentModels
from services.api.readiness import check_models

from schemas.domain import Principal

MODELS = DeploymentModels(
    extraction="qwen2.5:7b-instruct",
    vision="moondream:1.8b-v2-q4_K_M",
    transcription="Systran/faster-whisper-tiny.en",
    embedding="all-minilm:22m-l6-v2-fp16",
)


def _ollama(names: list[str] | None = None, *, status: int = 200, refuse: bool = False):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        if refuse:
            raise httpx.ConnectError("connection refused", request=request)
        if status != 200:
            return httpx.Response(status, json={"error": "unwell"})
        return httpx.Response(200, json={"models": [{"name": n, "model": n} for n in names or []]})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama:11434")


async def test_not_ready_until_the_extraction_model_is_present() -> None:
    async with _ollama(["moondream:1.8b-v2-q4_K_M", "all-minilm:22m-l6-v2-fp16"]) as http:
        report = await check_models(MODELS, http)
    assert report.ready is False
    by_role = {m.role: m for m in report.models}
    assert by_role["extraction"].present is False
    assert by_role["vision"].present and by_role["embedding"].present
    # Transcription is the Whisper sidecar's, not Ollama's: not reported from Ollama's list.
    assert "transcription" not in by_role
    async with _ollama(
        ["qwen2.5:7b-instruct", "moondream:1.8b-v2-q4_K_M", "all-minilm:22m-l6-v2-fp16"]
    ) as http:
        assert (await check_models(MODELS, http)).ready is True


async def test_a_model_is_present_only_under_its_own_tag() -> None:
    async with _ollama(
        ["qwen2.5:14b-instruct", "moondream:1.8b-v2-q4_K_M", "all-minilm:22m-l6-v2-fp16"]
    ) as http:
        assert (await check_models(MODELS, http)).ready is False
    bare = DeploymentModels(
        extraction="llama3",
        vision=MODELS.vision,
        transcription=MODELS.transcription,
        embedding=MODELS.embedding,
    )
    async with _ollama(
        ["llama3:latest", "moondream:1.8b-v2-q4_K_M", "all-minilm:22m-l6-v2-fp16"]
    ) as http:
        assert (await check_models(bare, http)).ready is True


@pytest.mark.parametrize("shape", ["refused", "500"])
async def test_an_ollama_that_does_not_answer_is_not_ready_and_says_so(shape: str) -> None:
    async with _ollama(status=500 if shape == "500" else 200, refuse=shape == "refused") as http:
        report = await check_models(MODELS, http)
    assert report.ready is False
    assert report.problem == "The model server did not answer."
    assert all(m.present is False for m in report.models)


async def test_no_configured_model_server_is_not_ready_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.api.readiness import deployment_readiness

    monkeypatch.delenv("OSPREY_OLLAMA_URL", raising=False)
    report = await deployment_readiness()
    assert report.ready is False
    assert report.problem == "No model server is configured for this deployment."


def test_the_route_needs_a_principal() -> None:
    response = TestClient(app).get("/v1/readiness")
    assert response.status_code in (401, 403)


def test_the_route_reports_for_any_signed_in_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app as app_module

    async def fake_readiness():  # type: ignore[no-untyped-def]
        return app_module.readiness_module.Readiness(ready=False, models=[], problem=None)

    monkeypatch.setattr(app_module.readiness_module, "deployment_readiness", fake_readiness)
    app.dependency_overrides[get_principal] = lambda: Principal(
        id="a", clearance="OFFICIAL", org_unit="u"
    )
    try:
        body = TestClient(app).get("/v1/readiness").json()
    finally:
        app.dependency_overrides.clear()
    assert body == {"ready": False, "models": [], "problem": None}
