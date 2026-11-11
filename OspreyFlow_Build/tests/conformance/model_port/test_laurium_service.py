"""Laurium's service itself (`06_DECISIONS.md` ADR-135 Amendment 6 decisions 4 and 5), its real code
with Laurium 0.6.0 and LangChain, every model call over real HTTP to the gateway's measured stand-in.

- **A setting naming any other host stops it at start** (planted at the real call site: the process
  environment the app reads when it is imported, as the image starts it).
- **Each refusal arrives as itself, never as an empty finding**: Laurium's `BatchExtractor` would turn
  a refused key, an unknown model or an unparseable answer into a row of `None`s. Each is planted in
  the stand-in (whose refusals are the real gateway's, measured) and asked through the Conduit's own
  adapter, so what is checked is what the Conduit sees.
- **Each call carries its tag and its engine's key to the gateway**, read off the stand-in.

The offline adapter tests hold `tests/adapters/extract_laurium/fake_service.py` to these same cases.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytest.importorskip("laurium", reason="Laurium is installed only in its own service's environment")

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig  # noqa: E402
from adapters.model_litellm.errors import (  # noqa: E402
    ExtractionFailedError,
    InvalidExtractionSchemaError,
    ModelLimitReached,
    ModelUnavailableError,
)
from adapters.model_litellm.usage import calling, engine_key, usage_tag  # noqa: E402
from adapters.model_litellm.stand_in import StandInGateway, StandInProvider  # noqa: E402
from schemas.model import ExtractionRequest  # noqa: E402

from .laurium_in_process import MASTER, MODEL, import_app, laurium_service, stand_in  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


def _request(**changes: Any) -> ExtractionRequest:
    fields: dict[str, Any] = {
        "document_id": "doc-1",
        "text": "Owen Wilson went to the store.",
        "json_schema": SCHEMA,
        "model": MODEL,
    }
    fields.update(changes)
    return ExtractionRequest(**fields)


async def _extract(gateway: StandInGateway, req: ExtractionRequest, key: str = MASTER) -> Any:
    with laurium_service(gateway) as transport:
        adapter = ExtractLauriumAdapter(
            LauriumConfig(base_url="http://laurium", gateway_key=key), transport=transport
        )
        try:
            return await adapter.extract(req)
        finally:
            await adapter.aclose()


# --- at start ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "named"),
    [
        ({"OSPREY_LAURIUM_GATEWAY_URL": "https://api.openai.com/v1"}, "OSPREY_LAURIUM_GATEWAY_URL"),
        ({}, "OSPREY_LAURIUM_GATEWAY_URL"),
        (
            {"OSPREY_LAURIUM_GATEWAY_URL": "http://litellm:4000", "OPENAI_BASE_URL": "https://x.example"},
            "OPENAI_BASE_URL",
        ),
        (
            {"OSPREY_LAURIUM_GATEWAY_URL": "http://litellm:4000", "LANGSMITH_TRACING": "true"},
            "LANGSMITH_TRACING",
        ),
    ],
)
def test_a_setting_naming_another_host_stops_the_service_at_start(
    env: dict[str, str], named: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("OPENAI_BASE_URL", "LANGSMITH_TRACING"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        if not name.startswith("OSPREY_LAURIUM_"):
            monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as stopped:
        import_app({k: v for k, v in env.items() if k.startswith("OSPREY_LAURIUM_")})
    assert stopped.value.code == 78
    assert named in capsys.readouterr().err


# --- through the gateway ---------------------------------------------------------------------------


async def test_a_finding_comes_back_through_the_gateway() -> None:
    gateway = stand_in()
    result = await _extract(gateway, _request())
    assert result.data == {"name": "Owen Wilson"}
    assert gateway.asked == [MODEL]


async def test_an_unparseable_answer_is_a_failure_after_three_tries_never_an_empty_finding() -> None:
    gateway = stand_in(answer="I could not find a name.")
    with pytest.raises(ExtractionFailedError, match="could not read"):
        await _extract(gateway, _request())
    assert gateway.asked == [MODEL] * 3


async def test_a_model_the_gateway_has_no_route_for_is_a_failure() -> None:
    gateway = stand_in()
    with pytest.raises(ExtractionFailedError) as caught:
        await _extract(gateway, _request(model="no-such-model"))
    assert "HTTP 400" in str(caught.value)
    assert "Invalid model name" not in str(caught.value)


async def test_a_wrong_gateway_key_is_a_failure_that_never_repeats_it() -> None:
    gateway = stand_in()
    with pytest.raises(ExtractionFailedError) as caught:
        await _extract(gateway, _request(), key="sk-wrong-key-WXYZ")
    assert "HTTP 401" in str(caught.value) and "WXYZ" not in str(caught.value)


async def test_a_model_the_provider_does_not_offer_is_model_unavailable() -> None:
    gateway = stand_in()
    gateway.providers = {"openai": StandInProvider("sk-provider", frozenset({"gpt-x"}))}
    _admin(gateway, "/model/new", {"model_name": "gemini",
                                   "litellm_params": {"model": "openai/not-offered",
                                                      "api_key": "sk-provider"}})  # fmt: skip
    _admin(gateway, "/key/generate", {"key": engine_key(MASTER, "gemini"), "key_alias": "g"})
    with calling("gemini", "extraction"), pytest.raises(ModelUnavailableError):
        await _extract(gateway, _request(model="gemini"))


async def test_an_engines_limit_is_model_limit_reached_and_its_tag_and_key_reach_the_gateway() -> None:
    gateway = stand_in()
    gateway.providers = {"openai": StandInProvider("sk-provider", frozenset({"gpt-x"}))}
    key = engine_key(MASTER, "gemini")
    _admin(gateway, "/model/new", {"model_name": "gemini",
                                   "litellm_params": {"model": "openai/gpt-x",
                                                      "api_key": "sk-provider"}})  # fmt: skip
    _admin(gateway, "/key/generate", {"key": key, "key_alias": "g", "rpm_limit": 1})
    with calling("gemini", "extraction"):
        await _extract(gateway, _request(model="gemini"))
        with pytest.raises(ModelLimitReached) as caught:
            await _extract(gateway, _request(model="gemini"))
    assert caught.value.kind == "requests"
    token, body = gateway.received[0]
    assert token == key
    assert usage_tag("gemini", "extraction") in body["metadata"]["tags"]


async def test_a_schema_laurium_is_not_given_is_refused_before_the_gateway() -> None:
    gateway = stand_in()
    schema = {"type": "object", "properties": {"a": {"oneOf": [{"type": "string"}]}}, "required": ["a"]}
    with pytest.raises(InvalidExtractionSchemaError):
        await _extract(gateway, _request(json_schema=schema))
    assert gateway.asked == []


async def test_the_gateway_unreachable_is_a_failure() -> None:
    with laurium_service(stand_in()) as transport:
        pass  # the stand-in is gone; the app module keeps its settings for the port it had
    adapter = ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium", gateway_key=MASTER), transport=transport
    )
    with pytest.raises(ExtractionFailedError, match="could not be reached"):
        await adapter.extract(_request())
    await adapter.aclose()


def _admin(gateway: StandInGateway, path: str, body: dict[str, Any]) -> None:
    with httpx.Client(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        resp = c.post(path, json=body, headers={"Authorization": f"Bearer {MASTER}"})
    assert resp.status_code == 200, resp.text
