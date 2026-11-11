"""Laurium's scoped key against the real gateway's admin routes (`06_DECISIONS.md` ADR-135
Amendment 6 decision 8; P12 part 1's review, round 2, item 2). Live: the stack's real LiteLLM
(`LITELLM_HOST`, `LITELLM_PORT`, `LITELLM_API_KEY`, as `LiteLLMConfig.from_env` reads them).

The key tested is **the token the adapter really sends Laurium's service** for a call outside the
routing, read off the request it makes (the service answered by a recorder that keeps the header and
refuses the call), not one this file derives itself: so a plant at the adapter's own call site
(`token = self._master`, `process/lanes/case-b/plants_P12.py --live`) reaches this test.

That token, held on the gateway as the deployment holds Laurium's key (`put_laurium_key`, the
conformance model alone), asks four admin routes, and each must be refused with 401 or 403:
`/key/generate` (a new key), `/key/update` (its own key widened to every model), `/key/delete` (a
decoy key the master key made) and `/model/new` (a model pointing nowhere). Nothing it asked for may
have happened: the decoy still held, its own key still naming the one model.

**A live test removes what it writes**, even when a route is wrongly granted: Laurium's key and the
decoy are deleted, and anything a granted route made (a key, a model, each given its own id here so
it can be found) is removed with the master key, then confirmed gone.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.extract_laurium.keys import delete_laurium_key, put_laurium_key
from adapters.model_litellm import CONFORMANCE_MODEL
from adapters.model_litellm.client import LiteLLMConfig
from adapters.model_litellm.errors import ExtractionFailedError
from schemas.model import ExtractionRequest

REFUSED = (401, 403)


async def _token_the_adapter_sends(master: str) -> str:
    """The bearer token the adapter sends Laurium's service for a call outside the routing."""
    seen: list[str] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(503, json={"refusal": "gateway_unreachable"})

    adapter = ExtractLauriumAdapter(
        LauriumConfig(base_url="http://laurium:8000", gateway_key=master),
        transport=httpx.MockTransport(_record),
    )
    try:
        with pytest.raises(ExtractionFailedError):
            await adapter.extract(
                ExtractionRequest(
                    document_id="doc-key-live",
                    text="Owen Wilson met Ada Byron.",
                    json_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                    model=CONFORMANCE_MODEL,
                )
            )
    finally:
        await adapter.aclose()
    assert len(seen) == 1 and seen[0].startswith("Bearer "), seen
    return seen[0].removeprefix("Bearer ")


async def _key_models(gateway: httpx.AsyncClient, master: str, key: str) -> list[str] | None:
    """The models the gateway holds `key` with, or None when it holds no such key."""
    resp = await gateway.get(
        "/key/info", params={"key": key}, headers={"Authorization": f"Bearer {master}"}
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    info: dict[str, Any] = resp.json().get("info") or {}
    return list(info.get("models") or [])


async def test_lauriums_key_is_refused_at_every_admin_route_of_the_real_gateway() -> None:
    config = LiteLLMConfig.from_env()
    master = config.api_key
    run = uuid.uuid4().hex[:12]
    planted_key = f"sk-osprey-p12-planted-{run}"
    decoy_key = f"sk-osprey-p12-decoy-{run}"
    planted_model = f"osprey-p12-planted-{run}"
    planted_model_id = f"osprey-p12-planted-{run}"
    admin = {"Authorization": f"Bearer {master}"}

    async with httpx.AsyncClient(base_url=config.base_url, timeout=30) as gateway:
        token = await _token_the_adapter_sends(master)
        try:
            held = await put_laurium_key(gateway, master, [CONFORMANCE_MODEL])
            decoy = await gateway.post(
                "/key/generate",
                json={
                    "key": decoy_key,
                    "models": [CONFORMANCE_MODEL],
                    "metadata": {"osprey_test": "p12-decoy"},
                },  # fmt: skip
                headers=admin,
            )
            assert decoy.status_code == 200, f"the master key made no decoy: {decoy.status_code}"

            scoped = {"Authorization": f"Bearer {token}"}
            asked = {
                "/key/generate": await gateway.post(
                    "/key/generate",
                    json={"key": planted_key, "models": [], "metadata": {"osprey_test": "p12"}},
                    headers=scoped,
                ),
                "/key/update": await gateway.post(
                    "/key/update", json={"key": held, "models": []}, headers=scoped
                ),
                "/key/delete": await gateway.post(
                    "/key/delete", json={"keys": [decoy_key]}, headers=scoped
                ),
                "/model/new": await gateway.post(
                    "/model/new",
                    json={
                        "model_name": planted_model,
                        "litellm_params": {
                            "model": "openai/osprey-planted",
                            "api_base": "http://127.0.0.1:9/v1",
                            "api_key": "sk-none",
                        },
                        "model_info": {"id": planted_model_id},
                    },  # fmt: skip
                    headers=scoped,
                ),
            }
            statuses = {route: resp.status_code for route, resp in asked.items()}
            assert all(code in REFUSED for code in statuses.values()), (
                f"Laurium's key was granted an admin route: {statuses}"
            )
            assert await _key_models(gateway, master, decoy_key) == [CONFORMANCE_MODEL]
            assert await _key_models(gateway, master, held) == [CONFORMANCE_MODEL]
        finally:
            # Remove what this test wrote, and whatever a wrongly granted route made.
            # One key a request: the gateway refuses a whole batch naming any key it does not
            # hold (measured; the stand-in models it).
            for key in (decoy_key, planted_key):
                await gateway.post("/key/delete", json={"keys": [key]}, headers=admin)
            await gateway.post("/model/delete", json={"id": planted_model_id}, headers=admin)
            await delete_laurium_key(gateway, master)
            assert await _key_models(gateway, master, decoy_key) is None
            assert await _key_models(gateway, master, planted_key) is None
            models = await gateway.get("/model/info", headers=admin)
            models.raise_for_status()
            assert planted_model not in models.text, "the planted model was left on the gateway"
