"""`ModelPort.extract`'s two engines for its suite (`06_DECISIONS.md` ADR-135 Amendments 5 and 6):
the LiteLLM adapter (Deep read) and Laurium's. Kept apart from `tests/conformance/registry.py`, which
imports every port's adapters, so Laurium's own 3.13 environment, which carries none of them, can run
the suite; the registry re-exports `MODEL_EXTRACT_ADAPTERS`.

Each factory's `context(gateway)` takes the gateway's measured stand-in, which every adapter reaches
over real HTTP as the gateway (`stand_in_http`), so both are held to one contract through one gateway
granting and refusing alike. `needs` names a module the adapter's other side needs where this run has
it not (Laurium's service code): the case is skipped with that reason, never silently dropped.
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.model_litellm.adapter import ModelLiteLLMAdapter
from adapters.model_litellm.client import LiteLLMClient, LiteLLMConfig
from ports.model import ModelPort

from .stand_in_http import serve


@dataclass(frozen=True)
class ExtractAdapterFactory:
    label: str
    context: Callable[[Any], AbstractAsyncContextManager[ModelPort]]
    needs: str | None = None

    def __str__(self) -> str:  # pytest parametrize id
        return self.label


@asynccontextmanager
async def _litellm(gateway: Any) -> AsyncIterator[ModelPort]:
    with serve(gateway) as port:
        client = LiteLLMClient(LiteLLMConfig(host="127.0.0.1", port=port, api_key=gateway.master_key))
        try:
            yield ModelLiteLLMAdapter(client, embed_model="unused")
        finally:
            await client.aclose()


@asynccontextmanager
async def _laurium(gateway: Any) -> AsyncIterator[ModelPort]:
    from .laurium_in_process import laurium_service

    with laurium_service(gateway) as transport:
        adapter = ExtractLauriumAdapter(
            LauriumConfig(base_url="http://laurium", gateway_key=gateway.master_key),
            transport=transport,
        )
        try:
            yield adapter  # type: ignore[misc]
        finally:
            await adapter.aclose()


MODEL_EXTRACT_ADAPTERS: list[ExtractAdapterFactory] = [
    ExtractAdapterFactory(label="model_litellm", context=_litellm),
    ExtractAdapterFactory(
        label="extract_laurium",
        context=_laurium,
        needs=None if importlib.util.find_spec("laurium") else "laurium",
    ),
]
