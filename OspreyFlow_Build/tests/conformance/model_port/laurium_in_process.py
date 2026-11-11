"""Laurium's service, its real code with Laurium and LangChain, reached in-process through
`httpx.ASGITransport`, its every model call going over real HTTP to the gateway's stand-in
(`stand_in_http`) under the name `litellm` (`06_DECISIONS.md` ADR-135 Amendment 6).

Runs only where Laurium is installed: Laurium's own Python 3.13 environment, built from
`services/laurium/requirements.txt` by hash (the `laurium-service` job in
`process/lanes/case-b/P12_CI.diff`). The Conduit's environment carries no Laurium, by design, so the
modules using this skip there at collection with that reason.
"""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType

import httpx

from adapters.model_litellm.stand_in import StandInGateway

from .stand_in_http import resolve_litellm_here, serve

MASTER = "sk-planted-laurium-master"
MODEL = "qwen2.5:0.5b-instruct"


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
    image starts it: its settings are read at import."""
    for name in list(os.environ):
        if name.startswith("OSPREY_LAURIUM_"):
            del os.environ[name]
    os.environ.update(env)
    sys.modules.pop("services.laurium.app", None)
    return importlib.import_module("services.laurium.app")


@contextmanager
def laurium_service(gateway: StandInGateway) -> Iterator[httpx.AsyncBaseTransport]:
    """A transport to the service, whose gateway is `gateway` served over HTTP as `litellm`."""
    with serve(gateway) as port, resolve_litellm_here():
        app = import_app({"OSPREY_LAURIUM_GATEWAY_URL": f"http://litellm:{port}"})
        yield httpx.ASGITransport(app=app.app)
