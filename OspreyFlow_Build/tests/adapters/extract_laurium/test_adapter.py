"""The thin `ModelPort.extract` adapter over Laurium's service (`06_DECISIONS.md` ADR-135
Amendment 6 decision 3), offline, against `fake_service.FakeLauriumService` and the measured gateway
stand-in behind it. The same cases against the real service are in
`tests/conformance/model_port/test_laurium_service.py`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.model_litellm.errors import (
    ExtractionFailedError,
    InvalidExtractionSchemaError,
    ModelLimitReached,
    ModelUnavailableError,
)
from adapters.model_litellm.stand_in import StandInGateway, StandInProvider
from adapters.model_litellm.usage import calling, engine_key, usage_tag
from schemas.model import ExtractionRequest
from tests.adapters.extract_laurium.fake_service import FakeLauriumService

MASTER = "sk-planted-master-0001"
MODEL = "qwen2.5:0.5b-instruct"
SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


def _gateway(answer: str = '{"name": "Owen Wilson"}') -> StandInGateway:
    return StandInGateway(
        master_key=MASTER,
        salt_key="salt",
        providers={"openai": StandInProvider("sk-provider", frozenset({"gpt-x"}))},
        config_models=frozenset({MODEL}),
        answer=answer,
    )


def _adapter(service: FakeLauriumService) -> ExtractLauriumAdapter:
    return ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key=MASTER),
        transport=service.transport(),
    )


def _request(**changes: Any) -> ExtractionRequest:
    fields: dict[str, Any] = {
        "document_id": "doc-1",
        "text": "Owen Wilson went to the store.",
        "json_schema": SCHEMA,
        "model": MODEL,
    }
    fields.update(changes)
    return ExtractionRequest(**fields)


async def test_a_finding_comes_back_in_the_requests_shape() -> None:
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    result = await adapter.extract(_request())
    await adapter.aclose()
    assert result.document_id == "doc-1"
    assert result.model == MODEL
    assert result.data == {"name": "Owen Wilson"}
    assert result.engine is None  # set by the routing, never by an adapter


async def test_a_malformed_schema_is_refused_before_the_service_is_called() -> None:
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    with pytest.raises(InvalidExtractionSchemaError):
        await adapter.extract(_request(json_schema={"type": "not-a-real-json-schema-type"}))
    await adapter.aclose()
    assert service.received == []


async def test_a_schema_laurium_is_not_given_is_an_invalid_schema() -> None:
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    with pytest.raises(InvalidExtractionSchemaError, match="oneOf"):
        await adapter.extract(
            _request(
                json_schema={
                    "type": "object",
                    "properties": {"a": {"oneOf": [{"type": "string"}]}},
                    "required": ["a"],
                }
            )
        )
    await adapter.aclose()


async def test_an_answer_that_does_not_fit_the_schema_is_never_trusted() -> None:
    """The service's own model check is Pydantic's; the adapter checks the answer against the
    request's JSON Schema itself, as the LiteLLM adapter does, before anything downstream reads it."""
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 50}},
        "required": ["name"],
        "additionalProperties": False,
    }
    with pytest.raises(ExtractionFailedError, match="schema"):
        await adapter.extract(_request(json_schema=schema))
    await adapter.aclose()


async def test_an_unparseable_answer_is_a_failure_never_an_empty_finding() -> None:
    service = FakeLauriumService(_gateway(answer="I could not find a name."))
    adapter = _adapter(service)
    with pytest.raises(ExtractionFailedError):
        await adapter.extract(_request())
    await adapter.aclose()


async def test_a_model_the_gateway_has_no_route_for_is_a_failure() -> None:
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    with pytest.raises(ExtractionFailedError) as caught:
        await adapter.extract(_request(model="no-such-model"))
    await adapter.aclose()
    assert "Invalid model name" not in str(caught.value)  # the gateway's words never pass on


async def test_a_model_the_provider_does_not_offer_is_model_unavailable() -> None:
    gateway = _gateway()
    _store_engine(gateway, "gemini", "openai/not-offered", "sk-provider")
    _virtual_key(gateway, engine_key(MASTER, "gemini"))
    service = FakeLauriumService(gateway)
    adapter = _adapter(service)
    with calling("gemini", "extraction"), pytest.raises(ModelUnavailableError):
        await adapter.extract(_request(model="gemini"))
    await adapter.aclose()


async def test_a_wrong_gateway_key_is_a_failure_that_never_repeats_the_key() -> None:
    service = FakeLauriumService(_gateway())
    adapter = ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key="sk-wrong-key-WXYZ"),
        transport=service.transport(),
    )
    with pytest.raises(ExtractionFailedError) as caught:
        await adapter.extract(_request())
    await adapter.aclose()
    assert "WXYZ" not in str(caught.value)


async def test_an_engines_call_carries_its_tag_and_its_own_key() -> None:
    gateway = _gateway()
    _store_engine(gateway, "gemini", "openai/gpt-x", "sk-provider")
    key = engine_key(MASTER, "gemini")
    _virtual_key(gateway, key)
    service = FakeLauriumService(gateway)
    adapter = _adapter(service)
    with calling("gemini", "extraction"):
        await adapter.extract(_request(model="gemini"))
    await adapter.aclose()
    token, body = service.received[-1]
    assert token == key
    assert body["tag"] == usage_tag("gemini", "extraction")
    assert gateway.received[-1][0] == key


async def test_a_local_call_goes_with_the_master_key_and_its_tag() -> None:
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    with calling("local", "extraction"):
        await adapter.extract(_request())
    await adapter.aclose()
    token, body = service.received[-1]
    assert token == MASTER
    assert body["tag"] == usage_tag("local", "extraction")


async def test_a_call_outside_the_routing_is_untagged_with_the_master_key() -> None:
    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    await adapter.extract(_request())
    await adapter.aclose()
    token, body = service.received[-1]
    assert token == MASTER
    assert body.get("tag") is None


async def test_an_engines_limit_is_model_limit_reached_in_our_words() -> None:
    gateway = _gateway()
    _store_engine(gateway, "gemini", "openai/gpt-x", "sk-provider")
    key = engine_key(MASTER, "gemini")
    _virtual_key(gateway, key, rpm_limit=1)
    service = FakeLauriumService(gateway)
    adapter = _adapter(service)
    with calling("gemini", "extraction"):
        await adapter.extract(_request(model="gemini"))
        with pytest.raises(ModelLimitReached) as caught:
            await adapter.extract(_request(model="gemini"))
    await adapter.aclose()
    assert caught.value.kind == "requests"
    assert key[-4:] not in str(caught.value)


async def test_a_text_over_the_services_limit_is_a_failure_not_a_cut() -> None:
    from services.laurium.app_contract import MAX_CHARS

    service = FakeLauriumService(_gateway())
    adapter = _adapter(service)
    with pytest.raises(ExtractionFailedError, match="long"):
        await adapter.extract(_request(text="a" * (MAX_CHARS + 1)))
    await adapter.aclose()


async def test_the_service_unreachable_is_a_failure() -> None:
    import httpx

    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key=MASTER),
        transport=httpx.MockTransport(_down),
    )
    with pytest.raises(ExtractionFailedError, match="reached"):
        await adapter.extract(_request())
    await adapter.aclose()


def _answering(status: int, content: bytes) -> ExtractLauriumAdapter:
    import httpx

    return ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key=MASTER),
        transport=httpx.MockTransport(lambda _: httpx.Response(status, content=content)),
    )


async def test_a_429_that_is_not_a_limit_never_repeats_the_gateways_words() -> None:
    """The one refusal whose gateway error the service forwards (`app.py`, for a 429), in its exact
    shape: a 429 the measured reader does not take for a limit, its words carrying part of a key.
    The adapter answers in its own words alone."""
    forwarded = {
        "refusal": "gateway",
        "gateway_status": 429,
        "gateway_error": {
            "type": "internal_server_error",
            "message": "No deployments available. Received API Key = sk-...WXYZ",
        },
    }
    adapter = _answering(502, json.dumps(forwarded).encode())
    with pytest.raises(ExtractionFailedError) as caught:
        await adapter.extract(_request())
    await adapter.aclose()
    assert not isinstance(caught.value, ModelLimitReached)
    assert "WXYZ" not in str(caught.value) and "deployments" not in str(caught.value)


@pytest.mark.parametrize(
    ("status", "content"),
    [(200, b"not json"), (200, b"[1, 2]"), (200, b'{"data": [1]}'), (502, b"not json"),
     (502, b"[1, 2]")],  # fmt: skip
)
async def test_an_answer_of_another_shape_is_a_typed_failure(status: int, content: bytes) -> None:
    adapter = _answering(status, content)
    with pytest.raises(ExtractionFailedError):
        await adapter.extract(_request())
    await adapter.aclose()


# --- the stand-in gateway's own set-up, through its admin routes ---------------------------------


def _admin(gateway: StandInGateway, path: str, body: dict[str, Any]) -> None:
    import httpx

    with httpx.Client(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        resp = c.post(path, json=body, headers={"Authorization": f"Bearer {MASTER}"})
    assert resp.status_code == 200, resp.text


def _store_engine(gateway: StandInGateway, name: str, model: str, key: str) -> None:
    _admin(
        gateway,
        "/model/new",
        {"model_name": name, "litellm_params": {"model": model, "api_key": key}},
    )


def _virtual_key(gateway: StandInGateway, key: str, **limits: Any) -> None:
    _admin(gateway, "/key/generate", {"key": key, "key_alias": f"alias-{key[-6:]}", **limits})


def test_the_fake_answers_json_the_stand_in_was_given() -> None:
    """The fake service's answer is the stand-in's own content, not something the fake makes up."""
    assert json.loads(_gateway().answer) == {"name": "Owen Wilson"}
