"""The live suite's Laurium factory never deletes a deployment's key (P12 part 2; the hazard carried
from part 1): `laurium_live_adapter` makes Laurium's key on the gateway it is pointed at and
deletes it after, so pointed at a gateway that **already** holds Laurium's key (a deployment's,
whose Laurium runs on it) it refuses before writing anything. Pointed at a test gateway, what it
made is gone after, even when the run fails.

Offline, in the Conduit's environment: the gateway's stand-in served over HTTP; the factory's guard
and its key's lifetime come before Laurium's own code is imported, which this environment does not
carry (so a run past the guard fails at that import, and its key is still removed).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

from adapters.extract_laurium.keys import METADATA, laurium_key
from tests.conformance.model_port.laurium_in_process import (
    MASTER,
    MODEL,
    laurium_live_adapter,
    stand_in,
)
from tests.conformance.model_port.stand_in_http import serve


@pytest.fixture
def gateway() -> Iterator[tuple[object, int]]:
    g = stand_in()
    with serve(g) as port:
        saved = {k: os.environ.get(k) for k in ("LITELLM_HOST", "LITELLM_PORT", "LITELLM_API_KEY")}
        os.environ.update(LITELLM_HOST="127.0.0.1", LITELLM_PORT=str(port), LITELLM_API_KEY=MASTER)
        try:
            yield g, port
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


async def test_a_gateway_already_holding_lauriums_key_is_refused_untouched(
    gateway: tuple[object, int],
) -> None:
    g, port = gateway
    with httpx.Client(base_url=f"http://127.0.0.1:{port}") as c:
        c.post(
            "/key/generate",
            json={"key": laurium_key(MASTER), "models": [MODEL], "metadata": METADATA},
            headers={"Authorization": f"Bearer {MASTER}"},
        ).raise_for_status()
    with pytest.raises(AssertionError, match="already holds Laurium's key"):
        async with laurium_live_adapter(MODEL):
            pass
    assert g.virtual_key(laurium_key(MASTER)) is not None  # type: ignore[attr-defined]


async def test_a_test_gateway_keeps_nothing_after(gateway: tuple[object, int]) -> None:
    g, _ = gateway
    with pytest.raises(ImportError):  # Laurium's own code is not in the Conduit's environment
        async with laurium_live_adapter(MODEL):
            pass
    assert g.virtual_key(laurium_key(MASTER)) is None  # type: ignore[attr-defined]
