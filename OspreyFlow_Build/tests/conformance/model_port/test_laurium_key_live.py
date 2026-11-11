"""Laurium's scoped key against the real gateway's admin routes (`06_DECISIONS.md` ADR-135
Amendment 6 decision 8, "with no admin right"; P12 part 1's review, round 2, item 2).

**Live, so skipped unless pointed at a gateway** (`OSPREY_LIVE_GATEWAY_URL`, its master key in
`OSPREY_LIVE_GATEWAY_MASTER`), as `tests/services/api/test_model_gateway_live.py` is: the pinned
LiteLLM **with its own database** (virtual keys are refused without one, so CI's `conformance-model`
gateway and the dev stack's cannot run this), holding the pinned conformance model, and never a
deployment's gateway (a gateway already holding Laurium's key is refused before anything is
written). No leased stack has a gateway; the run, its lease and the gateway it used are in
`process/lanes/case-b/P12_RED_RECORD.md`.

The key tested is **the token the adapter really sends Laurium's service** for a call outside the
routing, read off the request it makes (the service answered by a recorder that keeps the header and
refuses the call), so a plant at the adapter's own call site reaches it. It must be the key held on
the gateway as the deployment holds Laurium's (`put_laurium_key`: the conformance model alone), and
it must work there (a one-token chat call to that model is answered), so a token the gateway does
not know cannot pass as refused. It then asks four admin routes, and each must be refused (401 or
403) **as a key the gateway knows**, never as an unknown token: `/key/generate` (a new key),
`/key/update` (its own key widened to every model), `/key/delete` (a decoy key the master key made)
and `/model/new` (a model pointing nowhere). Nothing it asked for may have happened: the decoy still
held, its own key still naming the one model.

**A live test removes what it writes**, even when a route is wrongly granted, and each removal runs
whether or not another failed: Laurium's key, the decoy, any key carrying this run's tag (the one a
wrongly granted `/key/generate` made, whatever the gateway named it), and the planted model, by its
id. What is left is checked afterwards; when the test has already failed, what is left is printed
rather than raised, so the first failure stays the one reported.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from adapters.extract_laurium.adapter import ExtractLauriumAdapter, LauriumConfig
from adapters.extract_laurium.keys import delete_laurium_key, laurium_key, put_laurium_key
from adapters.model_litellm import CONFORMANCE_MODEL
from adapters.model_litellm.errors import ExtractionFailedError
from schemas.model import ExtractionRequest

URL = os.environ.get("OSPREY_LIVE_GATEWAY_URL", "")
MASTER = os.environ.get("OSPREY_LIVE_GATEWAY_MASTER", "")

pytestmark = pytest.mark.skipif(
    not (URL and MASTER),
    reason="live: set OSPREY_LIVE_GATEWAY_URL and OSPREY_LIVE_GATEWAY_MASTER (the pinned "
    "gateway with its own database, under a lease)",
)

REFUSED = (401, 403)
#: The words LiteLLM answers a token it does not hold with (measured; `stand_in.py` models them).
UNKNOWN_TOKEN = ("Invalid proxy server token", "token_not_found_in_db")


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


async def _key_models(gateway: httpx.AsyncClient, key: str) -> list[str] | None:
    """The models the gateway holds `key` with, or None when it holds no such key."""
    resp = await gateway.get(
        "/key/info", params={"key": key}, headers={"Authorization": f"Bearer {MASTER}"}
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    info: dict[str, Any] = resp.json().get("info") or {}
    return list(info.get("models") or [])


async def _tagged_keys(gateway: httpx.AsyncClient, tag: str) -> list[str]:
    """The hashes of every key the gateway holds carrying this run's tag."""
    resp = await gateway.get(
        "/key/list",
        params={"return_full_object": "true", "size": 100},
        headers={"Authorization": f"Bearer {MASTER}"},
    )
    resp.raise_for_status()
    return [
        str(k.get("token"))
        for k in resp.json().get("keys") or []
        if isinstance(k, dict) and (k.get("metadata") or {}).get("osprey_test") == tag
    ]


async def _model_ids(gateway: httpx.AsyncClient) -> list[str]:
    resp = await gateway.get("/model/info", headers={"Authorization": f"Bearer {MASTER}"})
    resp.raise_for_status()
    return [str((m.get("model_info") or {}).get("id")) for m in resp.json().get("data") or []]


async def _remove(
    gateway: httpx.AsyncClient, *, tag: str, keys: list[str], model_id: str
) -> list[str]:
    """Remove what the test, or a wrongly granted route, wrote; each step runs whatever another
    did. Returns what could not be removed or is still there."""
    admin = {"Authorization": f"Bearer {MASTER}"}
    problems: list[str] = []

    async def _try(what: str, step: Awaitable[None]) -> None:
        try:
            await step
        except Exception as exc:  # noqa: BLE001 - every removal runs; each failure is reported
            problems.append(f"{what}: {type(exc).__name__}: {exc}")

    async def _delete_key(key: str) -> None:
        # One key a request: the gateway refuses a whole batch naming a key it does not hold.
        resp = await gateway.post("/key/delete", json={"keys": [key]}, headers=admin)
        if resp.status_code not in (200, 404):
            raise AssertionError(f"/key/delete answered {resp.status_code}")

    async def _delete_model() -> None:
        resp = await gateway.post("/model/delete", json={"id": model_id}, headers=admin)
        if resp.status_code != 200 and not (resp.status_code == 400 and "not found" in resp.text):
            raise AssertionError(f"/model/delete answered {resp.status_code}")

    for key in keys:
        await _try(f"deleting a key ending {key[-4:]}", _delete_key(key))
    await _try("the run's tagged keys", _delete_tagged(gateway, tag, _delete_key))
    await _try("the planted model", _delete_model())
    await _try("Laurium's key", delete_laurium_key(gateway, MASTER))
    try:
        for key in keys:
            if await _key_models(gateway, key) is not None:
                problems.append(f"a key ending {key[-4:]} is still held")
        if await _tagged_keys(gateway, tag):
            problems.append("a key carrying this run's tag is still held")
        if model_id in await _model_ids(gateway):
            problems.append("the planted model is still held")
        if await _key_models(gateway, laurium_key(MASTER)) is not None:
            problems.append("Laurium's key is still held")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"checking what is left: {type(exc).__name__}: {exc}")
    return problems


async def _delete_tagged(
    gateway: httpx.AsyncClient, tag: str, delete: Callable[[str], Awaitable[None]]
) -> None:
    for token in await _tagged_keys(gateway, tag):
        await delete(token)


async def test_lauriums_key_is_refused_at_every_admin_route_of_the_real_gateway() -> None:
    run = uuid.uuid4().hex[:12]
    tag = f"p12-{run}"
    planted_key = f"sk-osprey-p12-planted-{run}"
    decoy_key = f"sk-osprey-p12-decoy-{run}"
    planted_model = f"osprey-p12-planted-{run}"
    admin = {"Authorization": f"Bearer {MASTER}"}

    async with httpx.AsyncClient(base_url=URL, timeout=60) as gateway:
        if await _key_models(gateway, laurium_key(MASTER)) is not None:
            pytest.fail(
                "This gateway already holds Laurium's key: it is a deployment's, not a test "
                "gateway. Nothing was written."
            )
        token = await _token_the_adapter_sends(MASTER)
        failed = True
        problems: list[str] = []
        try:
            held = await put_laurium_key(gateway, MASTER, [CONFORMANCE_MODEL])
            assert token == held, "the adapter did not send Laurium's own key"
            scoped = {"Authorization": f"Bearer {token}"}
            works = await gateway.post(
                "/chat/completions",
                json={
                    "model": CONFORMANCE_MODEL,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "Say yes."}],
                },  # fmt: skip
                headers=scoped,
            )
            assert works.status_code == 200, f"Laurium's key does not work: {works.status_code}"

            decoy = await gateway.post(
                "/key/generate",
                json={
                    "key": decoy_key,
                    "models": [CONFORMANCE_MODEL],
                    "metadata": {"osprey_test": tag},
                },  # fmt: skip
                headers=admin,
            )
            assert decoy.status_code == 200, f"the master key made no decoy: {decoy.status_code}"

            asked = {
                "/key/generate": await gateway.post(
                    "/key/generate",
                    json={"key": planted_key, "models": [], "metadata": {"osprey_test": tag}},
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
                        "model_info": {"id": planted_model},
                    },  # fmt: skip
                    headers=scoped,
                ),
            }
            for route, resp in asked.items():
                print(f"{route}: {resp.status_code} {resp.text[:200]}")
            statuses = {route: resp.status_code for route, resp in asked.items()}
            assert all(code in REFUSED for code in statuses.values()), (
                f"Laurium's key was granted an admin route: {statuses}"
            )
            unknown = [r for r, resp in asked.items() if any(w in resp.text for w in UNKNOWN_TOKEN)]
            assert not unknown, f"refused as an unknown token, not as Laurium's key: {unknown}"
            assert await _key_models(gateway, decoy_key) == [CONFORMANCE_MODEL]
            assert await _key_models(gateway, held) == [CONFORMANCE_MODEL]
            failed = False
        finally:
            problems = await _remove(
                gateway, tag=tag, keys=[decoy_key, planted_key], model_id=planted_model
            )
            if problems and failed:
                print(f"left on the gateway after the failure: {problems}")
    assert not problems, f"left on the gateway: {problems}"
