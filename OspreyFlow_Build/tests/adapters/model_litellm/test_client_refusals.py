"""The model proxy's refusals, as the real one answers them (CLAUDE.md rule 15) — ADR-095.

Seen on the owner's deployment, 6 October 2026: *Extract entities* answered "request failed: 500"
while the chosen extraction model was still downloading, because the proxy answers a model it
cannot serve with `404` and the client folded that into a generic failure that claimed three
attempts. What a mistake would do, and the case that catches it:

- a missing model reported as a malformed answer
  (`test_a_model_the_proxy_cannot_serve_is_unavailable_and_is_asked_once`);
- a missing model asked three times (the same test);
- a long extraction on a CPU-only model cut off at two minutes
  (`test_the_timeout_is_the_deployments`).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from adapters.model_litellm.errors import ExtractionFailedError, ModelUnavailableError

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


def _client(handler) -> tuple[LiteLLMClient, list[httpx.Request]]:  # type: ignore[no-untyped-def]
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return LiteLLMClient(LiteLLMConfig(), transport=httpx.MockTransport(record)), seen


def _extract(client: LiteLLMClient) -> object:
    return asyncio.run(
        client.extract_json(model="qwen2.5:7b-instruct", text="t", response_schema=SCHEMA)
    )


def test_a_model_the_proxy_cannot_serve_is_unavailable_and_is_asked_once() -> None:
    """The real proxy's answer while Ollama has not got the model: 404 with a JSON error."""
    client, seen = _client(
        lambda r: httpx.Response(
            404, json={"error": {"message": "model 'qwen2.5:7b-instruct' not found"}}
        )
    )
    with pytest.raises(ModelUnavailableError) as refused:
        _extract(client)
    assert "qwen2.5:7b-instruct" in str(refused.value)
    assert "3 attempt" not in str(refused.value)
    assert len(seen) == 1
    assert isinstance(refused.value, ExtractionFailedError)  # existing callers still catch it


def test_an_answer_that_never_fits_the_schema_is_still_retried() -> None:
    client, seen = _client(
        lambda r: httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"y": 1})}}]}
        )
    )
    with pytest.raises(ExtractionFailedError) as failed:
        _extract(client)
    assert not isinstance(failed.value, ModelUnavailableError)
    assert len(seen) == 3


def test_the_timeout_is_the_deployments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_MODEL_TIMEOUT_SECONDS", "900")
    assert LiteLLMConfig.from_env().timeout_seconds == 900
    monkeypatch.delenv("OSPREY_MODEL_TIMEOUT_SECONDS")
    assert LiteLLMConfig.from_env().timeout_seconds == 900  # the default: a CPU-only 7B is slow
