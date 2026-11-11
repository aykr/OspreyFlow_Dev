"""Laurium in the Conduit (`spec/06_DECISIONS.md` ADR-135 Amendments 6 and 9, P12 part 2): its place
inside the model routes, its own key made at start without ever stopping the Conduit, and its client
closed at shutdown. `app.py` calls these; each is tested offline
(`tests/services/api/test_laurium_start.py`).

- **Inside the routes** (`routed_model`): `RoutedModel` is given the composed model, so a call to
  Laurium keeps its engine, that engine's key and the dataset egress rules, as Deep read's does.
- **The key at start** (`LauriumKeyAtStart`): tried once at start and, while the gateway does not
  answer or refuses, again in the background, each wait twice the last up to ten minutes, as the
  model engines' reconciliation is (ADR-135 Amendment 3, `ModelAdmin.start`). Until the key is held,
  Laurium's calls alone are refused in words (`LauriumExtracts.ready`); every other call runs.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence

import httpx

from adapters.extract_laurium.composed import LauriumExtracts, extraction_from_env
from adapters.extract_laurium.keys import laurium_at_start
from ports.model import ModelPort

from .model_routing import DatasetEgressReader, ModelRoutes, RoutedModel

log = logging.getLogger(__name__)

#: As the engines' reconciliation: the first wait, and the longest.
FIRST_WAIT_SECONDS = 15.0
LONGEST_WAIT_SECONDS = 600.0


def routed_model(
    inner: ModelPort,
    *,
    routes: ModelRoutes,
    egress: DatasetEgressReader | None,
    environ: Mapping[str, str],
    master: str,
    ready: Callable[[], bool] | None = None,
) -> RoutedModel:
    """The Conduit's model: `inner` with Laurium extracting when the deployment chose it, inside
    the routes."""
    composed = extraction_from_env(inner, environ, master=master)
    if isinstance(composed, LauriumExtracts) and ready is not None:
        composed.ready = ready
    return RoutedModel(composed, routes=routes, egress=egress)


def lauriums(model: ModelPort) -> LauriumExtracts | None:
    """The composed model inside `model`'s routes, when the deployment chose Laurium."""
    inner = getattr(model, "_inner", model)
    return inner if isinstance(inner, LauriumExtracts) else None


async def close_laurium(model: ModelPort) -> None:
    """At shutdown: Laurium's client closed (the lane-reviewer's item 14)."""
    if (composed := lauriums(model)) is not None:
        await composed.aclose()


class LauriumKeyAtStart:
    """Laurium's own key held on the gateway, at start and until it is (decision 8)."""

    def __init__(
        self,
        gateway: httpx.AsyncClient,
        master: str,
        models: Sequence[str],
        *,
        retry_seconds: float = FIRST_WAIT_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._gateway, self._master, self._models = gateway, master, list(models)
        self._retry_seconds, self._sleep = retry_seconds, sleep
        self._done = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def held(self) -> bool:
        return self._done.is_set()

    async def _once(self) -> bool:
        try:
            await laurium_at_start(self._gateway, self._master, self._models)
        except Exception as failed:  # noqa: BLE001 - never stops the Conduit; said, then tried again
            log.warning(
                "Laurium's key is not yet held on the model gateway (%s); trying again.",
                type(failed).__name__,
            )
            return False
        self._done.set()
        return True

    async def start(self) -> None:
        """Tried once now; if that does not hold the key, again in the background. Returns at
        once."""
        if not await self._once():
            self._task = asyncio.create_task(self._keep_trying_after_first())

    async def _keep_trying_after_first(self) -> None:
        wait = self._retry_seconds
        while True:
            await self._sleep(wait)
            if await self._once():
                return
            wait = min(wait * 2, LONGEST_WAIT_SECONDS)

    async def wait(self) -> None:
        await self._done.wait()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
