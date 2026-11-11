"""Laurium's service, its real code with Laurium and LangChain, reached in-process through
`httpx.ASGITransport`, its every model call going over real HTTP under the name `litellm`
(`06_DECISIONS.md` ADR-135 Amendment 6): to the gateway's stand-in (`stand_in_http`, offline), or to
the stack's real LiteLLM and its pinned model (`laurium_live_adapter`, leased).

Every other name is refused at the lookup while the service runs (`resolve_litellm_here`), so a call
the service would send to any other host fails before it leaves, and the name is kept for the test.
The adapter goes with Laurium's own scoped key (decision 8), which the harness holds on the gateway
as the deployment would (`keys.put_laurium_key`), never the master key.

Runs only where Laurium is installed: Laurium's own Python 3.13 environment, built from
`services/laurium/requirements.txt` by hash (the `laurium-service` job in
`process/lanes/case-b/P12_CI.diff`). The Conduit's environment carries no Laurium, by design, so the
modules using this skip there at collection with that reason.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from types import ModuleType

import httpx

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.extract_laurium.keys import (
    METADATA,
    delete_laurium_key,
    laurium_key,
    put_laurium_key,
)
from adapters.model_litellm.stand_in import StandInGateway

from .stand_in_http import resolve_litellm_here, serve

MASTER = "sk-planted-laurium-master"
MODEL = "qwen2.5:0.5b-instruct"
#: The base Laurium's service is given in the tests: the OpenAI-compatible `/v1` the gateway serves.
#: Settings accept it bare too; `test_laurium_service.py` asks both.
BASE = "/v1"


def stand_in(answer: str = '{"name": "Owen Wilson"}') -> StandInGateway:
    return StandInGateway(
        master_key=MASTER,
        salt_key="salt",
        providers={},
        config_models=frozenset({MODEL}),
        answer=answer,
    )


def import_app(env: dict[str, str]) -> ModuleType:
    """`services.laurium.app` imported afresh with `env` as the whole of its Laurium settings, as the
    image starts it: its settings are read at import. The process environment is put back as it was
    afterwards, whether the import served or stopped."""
    saved = dict(os.environ)
    try:
        for name in list(os.environ):
            if name.startswith("OSPREY_LAURIUM_"):
                del os.environ[name]
        os.environ.update(env)
        sys.modules.pop("services.laurium.app", None)
        return importlib.import_module("services.laurium.app")
    finally:
        os.environ.clear()
        os.environ.update(saved)


@dataclass
class Running:
    """Laurium's service running in-process: a transport to it, the names it asked for other than
    `litellm` (each refused), and each request the gateway's stand-in received, as it arrived."""

    transport: httpx.AsyncBaseTransport
    refused: list[str]
    paths: list[str] = field(default_factory=list)


def register_laurium_key(gateway: StandInGateway, master: str) -> None:
    """Laurium's own key held on the stand-in as the deployment holds it (`put_laurium_key`'s fields:
    the deployment's own models alone, the service's tag), made with the gateway's master key."""
    with httpx.Client(transport=gateway.transport(), base_url="http://litellm:4000") as c:
        resp = c.post(
            "/key/generate",
            json={"key": laurium_key(master), "models": sorted(gateway.config_models),
                  "metadata": METADATA},  # fmt: skip
            headers={"Authorization": f"Bearer {master}"},
        )
    resp.raise_for_status()


@contextmanager
def laurium_service(gateway: StandInGateway, *, base: str = BASE) -> Iterator[Running]:
    """Laurium's service whose gateway is `gateway` served over HTTP as `litellm`, at `base`, with
    Laurium's own key held on it."""
    register_laurium_key(gateway, gateway.master_key)
    paths: list[str] = []
    with serve(gateway, paths=paths) as port, resolve_litellm_here() as refused:
        app = import_app({"OSPREY_LAURIUM_GATEWAY_URL": f"http://litellm:{port}{base}"})
        yield Running(httpx.ASGITransport(app=app.app), refused, paths)


async def _holds_lauriums_key(gateway: httpx.AsyncClient, master: str) -> bool:
    """Whether the gateway holds Laurium's key, by its SHA-256 in `/key/list` (every page); an
    answer that cannot be read counts as held, so nothing is written to a gateway that would not
    say."""
    import hashlib

    wanted = hashlib.sha256(laurium_key(master).encode()).hexdigest()
    page, pages = 1, 1
    while page <= pages:
        resp = await gateway.get(
            "/key/list",
            params={"return_full_object": "true", "page": page, "size": 100},
            headers={"Authorization": f"Bearer {master}"},
        )
        if resp.status_code != 200:
            return True
        body = resp.json()
        pages = int(body.get("total_pages") or 1)
        if any(str(dict(k).get("token")) == wanted for k in body.get("keys") or []):
            return True
        page += 1
    return False


@asynccontextmanager
async def laurium_live_adapter(model: str) -> AsyncIterator[ExtractLauriumAdapter]:
    """The Laurium adapter over the real service in-process, every call to the stack's real LiteLLM
    (`LITELLM_HOST`, `LITELLM_PORT`, `LITELLM_API_KEY`, as the LiteLLM adapter's own conformance
    factory reads them) under the name `litellm`. Laurium's own key is made on that gateway for
    `model` alone before, and deleted after, even when the test fails (a live test removes what it
    writes). Any name other than `litellm` the service asks for fails the run.

    **A gateway already holding Laurium's key is refused before anything is written** (P12 part 2,
    the hazard carried from part 1): it is a deployment's, and the teardown would delete the key
    that deployment's Laurium runs on."""
    from adapters.model_litellm.client import LiteLLMConfig

    config = LiteLLMConfig.from_env()
    async with httpx.AsyncClient(base_url=config.base_url, timeout=30) as gateway:
        # Looked for by its hash in the gateway's list, never by the key in an address (httpx logs
        # every address; the reviewer's item 4).
        if await _holds_lauriums_key(gateway, config.api_key):
            raise AssertionError(
                "This gateway already holds Laurium's key (or would not say): it is a "
                "deployment's, not a test gateway. Nothing was written."
            )
        await put_laurium_key(gateway, config.api_key, [model])
        try:
            with resolve_litellm_here(config.host) as refused:
                # In a `finally`: a call to another host fails inside the test too (as an
                # unreachable gateway), and this assertion, not that failure, must be what is read.
                try:
                    app = import_app(
                        {"OSPREY_LAURIUM_GATEWAY_URL": f"http://litellm:{config.port}{BASE}"}
                    )
                    adapter = ExtractLauriumAdapter(
                        LauriumConfig(base_url="http://laurium", gateway_key=config.api_key),
                        transport=httpx.ASGITransport(app=app.app),
                    )
                    try:
                        yield adapter
                    finally:
                        await adapter.aclose()
                finally:
                    assert refused == [], f"Laurium's service asked for another host: {refused}"
        finally:
            await delete_laurium_key(gateway, config.api_key)
