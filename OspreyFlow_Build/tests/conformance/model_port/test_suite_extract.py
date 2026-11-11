"""`ModelPort.extract`'s conformance suite on both engines (`06_DECISIONS.md` ADR-135 Amendments 5
and 6): the LiteLLM adapter (Deep read) and Laurium's (`adapters/extract_laurium` and its service),
parametrised over `MODEL_EXTRACT_ADAPTERS`.

Both reach the gateway's measured stand-in over real HTTP as the gateway (`stand_in_http`), so the
two are held to one contract through one gateway that grants and refuses as the pinned LiteLLM does
(rule 15's second worked example). The stand-in answers as a model would, with the text it was
given; what is proved is the contract (schema in, schema-conforming output out, a malformed schema
refused before any model call, a refusal never an empty finding), not extraction quality, as
`test_suite.py`'s own extract cases prove it against the real proxy and the pinned model.

The Laurium case needs Laurium's service code, installed only in its own 3.13 environment; in the
Conduit's environment it is skipped with that reason (the `laurium-service` CI job runs it).
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.model_litellm import CONFORMANCE_MODEL
from adapters.model_litellm.errors import ExtractionFailedError, InvalidExtractionSchemaError
from adapters.model_litellm.stand_in import StandInGateway
from schemas.model import ExtractionRequest
from tests.conformance.model_port.extract_engines import (
    MODEL_EXTRACT_ADAPTERS,
    ExtractAdapterFactory,
)

MASTER = "sk-planted-conformance-master"
SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


def _gateway(answer: str) -> StandInGateway:
    return StandInGateway(
        master_key=MASTER,
        salt_key="salt",
        providers={},
        config_models=frozenset({CONFORMANCE_MODEL}),
        answer=answer,
    )


@pytest.fixture(params=MODEL_EXTRACT_ADAPTERS, ids=str)
def factory(request: pytest.FixtureRequest) -> ExtractAdapterFactory:
    chosen: ExtractAdapterFactory = request.param
    if chosen.needs:
        pytest.skip(f"{chosen.label} needs {chosen.needs}, installed only in its own environment")
    return chosen


def _request(**changes: Any) -> ExtractionRequest:
    fields: dict[str, Any] = {
        "document_id": "doc-1",
        "text": "Extract the person's name mentioned: Owen Wilson went to the store.",
        "json_schema": SCHEMA,
        "model": CONFORMANCE_MODEL,
    }
    fields.update(changes)
    return ExtractionRequest(**fields)


async def test_extract_returns_data_conforming_to_the_requested_schema(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": "Owen Wilson"}')
    async with factory.context(gateway) as adapter:
        result = await adapter.extract(_request())
    assert result.document_id == "doc-1"
    assert result.model == CONFORMANCE_MODEL
    assert result.data == {"name": "Owen Wilson"}
    assert result.engine is None
    assert gateway.asked == [CONFORMANCE_MODEL]


async def test_extract_rejects_a_malformed_schema_before_calling_the_model(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": "Owen Wilson"}')
    async with factory.context(gateway) as adapter:
        with pytest.raises(InvalidExtractionSchemaError):
            await adapter.extract(_request(json_schema={"type": "not-a-real-json-schema-type"}))
    assert gateway.asked == []


async def test_extract_never_returns_an_answer_that_does_not_fit_the_schema(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": 42}')
    async with factory.context(gateway) as adapter:
        with pytest.raises(ExtractionFailedError):
            await adapter.extract(_request())


async def test_extract_through_a_gateway_that_refuses_its_token_is_a_failure(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": "Owen Wilson"}')
    gateway.master_key = "sk-another-master-the-adapter-does-not-hold"
    async with factory.context(_with_key(gateway, MASTER)) as adapter:
        with pytest.raises(ExtractionFailedError):
            await adapter.extract(_request())
    assert gateway.asked == []


async def test_extract_of_a_model_the_gateway_has_no_route_for_is_a_failure(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": "Owen Wilson"}')
    async with factory.context(gateway) as adapter:
        with pytest.raises(ExtractionFailedError):
            await adapter.extract(_request(model="no-such-model"))


class _with_key:  # noqa: N801
    """The gateway as the adapter is configured for it: `master_key` is what the adapter sends,
    while the gateway itself holds another, so its token is refused."""

    def __init__(self, gateway: StandInGateway, sent: str) -> None:
        self._gateway = gateway
        self.master_key = sent

    def __getattr__(self, name: str) -> Any:
        return getattr(self._gateway, name)
