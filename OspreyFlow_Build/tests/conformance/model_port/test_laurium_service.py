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

from adapters.extract_laurium.keys import laurium_key  # noqa: E402

from .laurium_in_process import (  # noqa: E402
    BASE,
    MASTER,
    MODEL,
    import_app,
    laurium_service,
    stand_in,
)
from .stand_in_http import resolve_litellm_here, serve  # noqa: E402

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


async def _extract(
    gateway: StandInGateway, req: ExtractionRequest, key: str = MASTER, *, base: str = BASE
) -> Any:
    with laurium_service(gateway, base=base) as running:
        adapter = ExtractLauriumAdapter(
            LauriumConfig(base_url="http://laurium", gateway_key=key), transport=running.transport
        )
        try:
            return await adapter.extract(req)
        finally:
            await adapter.aclose()
            # Decision 4, read at the lookup: the service asked for no host but the gateway's.
            assert running.refused == [], f"Laurium's service asked for {running.refused}"


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
    # Decision 8: granted as Laurium's own scoped key, never the master key.
    assert [token for token, _ in gateway.received] == [laurium_key(MASTER)]


@pytest.mark.parametrize("base", ["/v1", ""])
async def test_every_model_call_goes_to_the_gateway_and_no_other_host(base: str) -> None:
    """Decision 4 at the call that picks the host: Laurium's `create_llm` given the gateway as
    `openai_api_base`, at either base the settings accept. Every other name is refused at the
    lookup and kept, so a call bound anywhere else is seen here, never sent."""
    gateway = stand_in()
    with laurium_service(gateway, base=base) as running:
        adapter = ExtractLauriumAdapter(
            LauriumConfig(base_url="http://laurium", gateway_key=MASTER),
            transport=running.transport,
        )
        try:
            result = await adapter.extract(_request())
        except ExtractionFailedError:
            result = None  # read below: which host was asked comes first
        finally:
            await adapter.aclose()
    assert running.refused == []  # a call bound elsewhere names its host here
    assert running.paths == [f"POST {base}/chat/completions"]
    assert result is not None and result.data == {"name": "Owen Wilson"}


def test_the_lookup_refuses_every_name_but_the_gateways() -> None:
    """Rule 15: the fixture the test above relies on refuses another name, as asked, and keeps it."""
    import socket

    with resolve_litellm_here() as refused:
        assert socket.getaddrinfo("litellm", 80)
        for name in ("api.openai.com", b"api.anthropic.com", "localhost", "127.0.0.1"):
            with pytest.raises(socket.gaierror):
                socket.getaddrinfo(name, 443)
    assert refused == ["api.openai.com", "api.anthropic.com", "localhost", "127.0.0.1"]


async def test_an_unparseable_answer_is_a_failure_after_three_tries_never_an_empty_finding() -> None:
    gateway = stand_in(answer="I could not find a name.")
    with pytest.raises(ExtractionFailedError, match="could not read"):
        await _extract(gateway, _request())
    assert gateway.asked == [MODEL] * 3


async def test_a_model_the_gateway_has_no_route_for_is_a_failure() -> None:
    """Laurium's key names the deployment's own models alone, so the gateway refuses another model
    on the key (403, `key_model_access_denied`, measured) before it looks for a route."""
    gateway = stand_in()
    with pytest.raises(ExtractionFailedError) as caught:
        await _extract(gateway, _request(model="no-such-model"))
    assert "HTTP 403" in str(caught.value)
    assert "only access models" not in str(caught.value)


async def test_a_wrong_gateway_key_is_a_failure_that_never_repeats_it() -> None:
    """The gateway's 401 names the last four characters of the key it was sent (measured): here the
    key derived from a master key the gateway does not hold."""
    gateway = stand_in()
    with pytest.raises(ExtractionFailedError) as caught:
        await _extract(gateway, _request(), key="sk-wrong-key-WXYZ")
    sent = laurium_key("sk-wrong-key-WXYZ")
    assert "HTTP 401" in str(caught.value) and sent[-4:] not in str(caught.value)


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
    # One call each: the OpenAI client inside LangChain retries a 429 or a 5xx twice by default,
    # which would spend the engine's requests on refusals and wait out each retry.
    assert len(gateway.received) == 2  # every chat request as it arrived, refused or not
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
    """`litellm` still resolves here; only its port is closed, so this is the gateway not
    answering, never a name lookup that failed."""
    with resolve_litellm_here():
        with serve(stand_in()) as port:
            app = import_app({"OSPREY_LAURIUM_GATEWAY_URL": f"http://litellm:{port}"})
        # The stand-in is shut down; the app keeps the port it was given.
        adapter = ExtractLauriumAdapter(
            LauriumConfig(base_url="http://laurium", gateway_key=MASTER),
            transport=httpx.ASGITransport(app=app.app),
        )
        with pytest.raises(ExtractionFailedError, match="could not be reached"):
            await adapter.extract(_request())
        await adapter.aclose()


async def test_the_real_service_refuses_a_call_without_the_gateways_token() -> None:
    gateway = stand_in()
    with laurium_service(gateway) as running:
        async with httpx.AsyncClient(transport=running.transport, base_url="http://laurium") as client:
            resp = await client.post("/v1/extract", json=_request().model_dump(mode="json"))
    assert (resp.status_code, resp.json()) == (401, {"refusal": "no_gateway_token"})
    assert gateway.asked == []


async def test_the_real_service_refuses_a_text_over_its_limit_never_reading_part() -> None:
    from services.laurium.app_contract import MAX_CHARS

    gateway = stand_in()
    with pytest.raises(ExtractionFailedError, match="too long"):
        await _extract(gateway, _request(text="a" * (MAX_CHARS + 1)))
    assert gateway.asked == []


def _admin(gateway: StandInGateway, path: str, body: dict[str, Any]) -> None:
    with httpx.Client(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        resp = c.post(path, json=body, headers={"Authorization": f"Bearer {MASTER}"})
    assert resp.status_code == 200, resp.text
