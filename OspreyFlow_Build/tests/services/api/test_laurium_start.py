"""Laurium at the Conduit's start (`06_DECISIONS.md` ADR-135 Amendment 6 decision 8; Amendment 9;
the lane-reviewer's items 1, 5 and 14 on P12 part 2).

- **A key that cannot be made at start never stops the Conduit** (item 1), as the model engines'
  reconciliation never does (ADR-135 Amendment 3, `ModelAdmin.start`): tried once, then again in
  the background, each wait twice the last up to ten minutes, logged in words and never the key.
  Until it is held, **Laurium's calls alone are refused in words**; every other model call runs.
- **Laurium sits inside the routes** (item 5): `routed_model` gives `RoutedModel` the composed
  model, so each call keeps its engine, its key and the egress rules. The reversed wrapping (routes
  inside Laurium's composition) is what the plant makes, and these fail on it.
- **Laurium's client is closed at shutdown** (item 14).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from services.api.laurium_start import LauriumKeyAtStart, routed_model
from services.api.model_routing import ModelRoutes, RoutedModel

from adapters.extract_laurium.composed import LauriumExtracts, laurium_reads
from adapters.extract_laurium.keys import laurium_key
from adapters.model_litellm.errors import ExtractionFailedError
from adapters.model_litellm.stand_in import StandInGateway
from schemas.model import ExtractionRequest, ExtractionResult

MASTER = "sk-planted-master-start"
MODEL = "qwen2.5:7b-instruct"
LAURIUM_ENV = {"OSPREY_EXTRACTION_ENGINE": "laurium", "OSPREY_LAURIUM_URL": "http://laurium:8000"}


class _Inner:
    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult(document_id=req.document_id, model=req.model, data={"by": "inner"})

    async def transcribe(self, req: Any) -> Any:
        return "transcript"

    async def describe_image(self, req: Any) -> Any:
        return "analysis"

    async def embed(self, texts: Sequence[str]) -> Any:
        return [[0.0]]


def _routes() -> ModelRoutes:
    from services.api.config import DeploymentModels
    from services.api.model_routing import routes_from_env

    return routes_from_env(DeploymentModels.from_env(), {})


def test_laurium_sits_inside_the_routes() -> None:
    model = routed_model(_Inner(), routes=_routes(), egress=None, environ=LAURIUM_ENV, master=MASTER)  # type: ignore[arg-type]
    assert isinstance(model, RoutedModel)
    assert isinstance(model._inner, LauriumExtracts)  # noqa: SLF001 - the composition is the claim


def test_not_chosen_the_routes_hold_the_model_as_it_was() -> None:
    inner = _Inner()
    model = routed_model(inner, routes=_routes(), egress=None, environ={}, master=MASTER)  # type: ignore[arg-type]
    assert isinstance(model, RoutedModel) and model._inner is inner  # noqa: SLF001


class _Gateway:
    """The stand-in, down for the first `down` attempts (a gateway still starting)."""

    def __init__(self, down: int) -> None:
        self.stand_in = StandInGateway(
            master_key=MASTER, salt_key="s", providers={}, config_models=frozenset({MODEL})
        )
        self.down = down
        self.tries = 0

    def transport(self) -> httpx.AsyncBaseTransport:
        inner = self.stand_in.transport()

        async def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/key/update":
                self.tries += 1
            if self.tries <= self.down:
                raise httpx.ConnectError("the gateway is not up yet")
            return await inner.handle_async_request(request)

        return httpx.MockTransport(handle)


async def test_a_gateway_still_starting_is_tried_again_without_stopping_anything(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = _Gateway(down=2)
    waits: list[float] = []

    async def no_wait(seconds: float) -> None:
        waits.append(seconds)

    async with httpx.AsyncClient(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        start = LauriumKeyAtStart(c, MASTER, [MODEL], retry_seconds=15, sleep=no_wait)
        with caplog.at_level(logging.WARNING):
            await start.start()  # returns at once, whatever the gateway says
            assert start.held is False
            await asyncio.wait_for(start.wait(), timeout=5)
    assert start.held is True
    assert gateway.stand_in.virtual_key(laurium_key(MASTER)) is not None
    assert waits == [15, 30], "each wait twice the last"
    assert "Laurium's key" in caplog.text and MASTER not in caplog.text
    assert laurium_key(MASTER) not in caplog.text


async def test_until_its_key_is_held_lauriums_calls_alone_are_refused_in_words() -> None:
    gateway = _Gateway(down=10_000)

    async def no_wait(seconds: float) -> None:
        await asyncio.sleep(0)

    async with httpx.AsyncClient(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        start = LauriumKeyAtStart(c, MASTER, [MODEL], sleep=no_wait)
        await start.start()
        model = routed_model(
            _Inner(), routes=_routes(), egress=None, environ=LAURIUM_ENV, master=MASTER,  # type: ignore[arg-type]
            ready=lambda: start.held,
        )
        request = ExtractionRequest(document_id="d", text="t", json_schema={"type": "object"}, model=MODEL)
        with laurium_reads(), pytest.raises(ExtractionFailedError, match="Laurium's key is not yet"):
            await model.extract(request)
        assert (await model.extract(request)).data == {"by": "inner"}  # Deep read's callers run
        await start.stop()


async def test_lauriums_client_is_closed_at_shutdown() -> None:
    model = routed_model(_Inner(), routes=_routes(), egress=None, environ=LAURIUM_ENV, master=MASTER)  # type: ignore[arg-type]
    composed = model._inner  # noqa: SLF001
    assert isinstance(composed, LauriumExtracts)
    from services.api.laurium_start import close_laurium

    await close_laurium(model)
    assert composed.laurium._http.is_closed  # noqa: SLF001
