"""`ModelPort.extract`'s refusals on both engines (`06_DECISIONS.md` ADR-135 Amendments 5 and 6): the
LiteLLM adapter (Deep read) and Laurium's (`adapters/extract_laurium` and its service), parametrised
over `MODEL_EXTRACT_ADAPTERS`, through the gateway's measured stand-in served over real HTTP as the
gateway (`stand_in_http`).

**Only what the real gateway and model cannot be made to do on demand is here**: an answer that breaks
the schema's type or one of its constraints, a gateway that refuses the token, a model with no route.
The stand-in answers whatever it is told to, whatever the prompt says, so it proves nothing of a
model's answer to Laurium's prompt. The contract's own cases (a conforming answer from the pinned
model, a malformed schema refused before any call) are `test_suite.py`'s, run on both engines
through `registry.MODEL_PORT_ADAPTERS` against the stack's real LiteLLM and the pinned conformance
model.

The Laurium case needs Laurium's service code, installed only in its own 3.13 environment; in the
Conduit's environment it is skipped with that reason (the `laurium-service` CI job runs it).
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.model_litellm import CONFORMANCE_MODEL
from adapters.model_litellm.errors import ExtractionFailedError
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


async def test_extract_never_returns_an_answer_that_does_not_fit_the_schema(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": 42}')
    async with factory.context(gateway) as adapter:
        with pytest.raises(ExtractionFailedError):
            await adapter.extract(_request())
    assert gateway.asked  # refused for the answer, after the model was asked


async def test_extract_checks_the_answer_against_every_constraint_of_the_schema(
    factory: ExtractAdapterFactory,
) -> None:
    """A string the model gives that breaks `minLength`: Laurium's parser takes the type alone, so
    this reaches the adapter's own check of the answer against the request's schema."""
    gateway = _gateway('{"name": "Owen Wilson"}')
    schema = {**SCHEMA, "properties": {"name": {"type": "string", "minLength": 50}}}
    async with factory.context(gateway) as adapter:
        with pytest.raises(ExtractionFailedError):
            await adapter.extract(_request(json_schema=schema))
    assert gateway.asked


async def test_extract_through_a_gateway_that_refuses_its_token_is_a_failure(
    factory: ExtractAdapterFactory,
) -> None:
    gateway = _gateway('{"name": "Owen Wilson"}')
    held = _with_key(gateway, "sk-another-master-the-gateway-does-not-hold")
    async with factory.context(held) as adapter:
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
    """The gateway as the adapter is configured for it: `master_key` is what the adapter holds, while
    the gateway itself (`held_by`) holds another, so every key the adapter sends or derives is
    refused."""

    def __init__(self, gateway: StandInGateway, sent: str) -> None:
        self.held_by = gateway
        self.master_key = sent

    def __getattr__(self, name: str) -> Any:
        return getattr(self.held_by, name)
