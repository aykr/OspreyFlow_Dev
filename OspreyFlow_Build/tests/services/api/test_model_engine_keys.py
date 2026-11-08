"""Each engine's own gateway key (`06_DECISIONS.md` ADR-135 Amendment 3, "As built in P3"): it may
call its own engine's models and no other, a key the current master key would not derive is revoked
at the next reconcile, and a gateway answering nonsense at start never stops the Conduit starting.

The gateway is the stand-in (`adapters.model_litellm.stand_in`), whose own proof of each measured
answer used here (a key's `models`, `/key/list`'s pages, a delete by hash) is
`tests/adapters/model_litellm/test_stand_in_gateway_usage.py`. Each case was shown red first
(`process/lanes/platform/P3_RED_RECORD.md`).
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from services.api.model_admin import (
    GatewayAdmin,
    InMemoryModelAdminAudit,
    Installed,
    ModelAdmin,
    ModelAdminRefused,
    ModelSettingsFile,
)

from adapters.model_litellm.stand_in import StandInGateway, StandInProvider
from adapters.model_litellm.usage import engine_key
from schemas.deployment import ModelProviderConfig
from schemas.model_admin import EngineLimits

OLD_MASTER = "sk-stand-in-master-OLD1"
NEW_MASTER = "sk-stand-in-master-NEW2"
GOOD = "sk-good-provider-key"
GEMINI = {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini-2.5-flash"}}
OPENAI = {"name": "openai", "label": "OpenAI", "roles": {"extraction": "gpt-4.1-mini"}}


def _gateway() -> StandInGateway:
    return StandInGateway(
        master_key=OLD_MASTER,
        salt_key="salt-one",
        providers={
            "gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash"}), 17, 5),
            "openai": StandInProvider(GOOD, frozenset({"gpt-4.1-mini"}), 17, 5),
        },
    )


def _admin(tmp_path: Path, gateway: StandInGateway, master: str,
           transport: httpx.AsyncBaseTransport | None = None) -> ModelAdmin:  # fmt: skip
    http = httpx.AsyncClient(base_url="http://litellm:4000",
                             transport=transport or gateway.transport(),
                             headers={"Authorization": f"Bearer {master}"})  # fmt: skip
    return ModelAdmin(
        installed=Installed(providers=[], defaults={}, key_present={}, local_only=False,
                            sendable=["O"], locals={"extraction": "qwen", "vision": None,
                                                    "transcription": None, "embedding": None}),
        settings_file=ModelSettingsFile(tmp_path / "model-settings"),
        gateway=GatewayAdmin(http),
        audit=InMemoryModelAdminAudit(),
        retry_seconds=0.001,
    )  # fmt: skip


async def _chat(gateway: StandInGateway, key: str, model: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url="http://litellm:4000", transport=gateway.transport(),
                                 headers={"Authorization": f"Bearer {key}"}) as client:  # fmt: skip
        return await client.post("/chat/completions", json={
            "model": model, "messages": [{"role": "user", "content": "hi"}]})  # fmt: skip


async def test_one_engine_s_key_is_refused_on_another_engine_s_models(tmp_path: Path) -> None:
    gateway = _gateway()
    admin = _admin(tmp_path, gateway, OLD_MASTER)
    for engine in (GEMINI, OPENAI):
        await admin.add_engine("admin-1", ModelProviderConfig.model_validate(engine))
    gemini_key = engine_key(OLD_MASTER, "gemini")
    held = gateway.virtual_key(gemini_key)
    assert held is not None and held.models == ["gemini/gemini-2.5-flash"]
    refused = await _chat(gateway, gemini_key, "openai/gpt-4.1-mini")
    assert refused.status_code == 403 and "key_model_access_denied" in refused.text
    # And an engine edited to another model has its key's models changed with it.
    await admin.edit_engine("admin-1", "gemini", ModelProviderConfig.model_validate(
        {**GEMINI, "roles": {"extraction": "gemini-2.5-pro"}}))  # fmt: skip
    held = gateway.virtual_key(gemini_key)
    assert held is not None and held.models == ["gemini/gemini-2.5-pro"]


async def test_a_changed_master_key_revokes_every_engine_key_the_new_one_would_not_derive(
    tmp_path: Path,
) -> None:
    """After a master-key rotation the old engine keys stay valid for whoever holds the old master
    key; the next start revokes each key tagged `osprey_engine` that the current master key would
    not derive, and leaves every other key alone."""
    gateway = _gateway()
    old = _admin(tmp_path, gateway, OLD_MASTER)
    for engine in (GEMINI, OPENAI):
        await old.add_engine("admin-1", ModelProviderConfig.model_validate(engine))
    async with httpx.AsyncClient(base_url="http://litellm:4000", transport=gateway.transport(),
                                 headers={"Authorization": f"Bearer {OLD_MASTER}"}) as master:
        await master.post("/key/generate", json={"key": "sk-not-ours-0001",
                                                 "metadata": {"team": "x"}})  # fmt: skip
    old_keys = {engine_key(OLD_MASTER, "gemini"), engine_key(OLD_MASTER, "openai")}
    assert old_keys <= set(gateway.virtual_keys())

    gateway.master_key = NEW_MASTER  # the gateway restarted under a new master key
    new = _admin(tmp_path, gateway, NEW_MASTER)
    await new.start()
    held = set(gateway.virtual_keys())
    assert not old_keys & held
    assert {engine_key(NEW_MASTER, "gemini"), engine_key(NEW_MASTER, "openai")} <= held
    assert "sk-not-ours-0001" in held
    refused = await _chat(gateway, engine_key(OLD_MASTER, "gemini"), "gemini/gemini-2.5-flash")
    assert refused.status_code == 401
    # The keys were named by their hash alone: no old key ever travelled in a request.
    sent = " ".join(gateway.seen)
    for key in old_keys:
        assert hashlib.sha256(key.encode()).hexdigest() in sent


async def test_every_page_of_the_gateway_s_keys_is_read_before_revoking(tmp_path: Path) -> None:
    """More stale keys than one page holds (measured: at most 100): every page is read first."""
    gateway = _gateway()
    admin = _admin(tmp_path, gateway, OLD_MASTER)
    await admin.add_engine("admin-1", ModelProviderConfig.model_validate(GEMINI))
    async with httpx.AsyncClient(base_url="http://litellm:4000", transport=gateway.transport(),
                                 headers={"Authorization": f"Bearer {OLD_MASTER}"}) as master:
        for i in range(150):
            await master.post("/key/generate", json={
                "key": f"sk-stale-{i:04d}", "metadata": {"osprey_engine": f"gone{i}"}})  # fmt: skip
    await _admin(tmp_path, gateway, OLD_MASTER).start()
    assert set(gateway.virtual_keys()) == {engine_key(OLD_MASTER, "gemini")}


async def test_a_garbled_first_answer_never_stops_the_conduit_starting(tmp_path: Path) -> None:
    """A 200 that is not JSON on the very first reconcile: `start` returns, and the retry finishes
    the work once the gateway answers properly."""
    gateway = _gateway()
    await _admin(tmp_path, gateway, OLD_MASTER).add_engine(
        "admin-1", ModelProviderConfig.model_validate(GEMINI))  # fmt: skip
    gateway._keys.clear()
    state = {"garbled": 3}
    real = gateway.transport()

    async def odd(request: httpx.Request) -> httpx.Response:
        if state["garbled"]:
            state["garbled"] -= 1
            return httpx.Response(200, content=b"<html>not json</html>")
        return await real.handle_async_request(request)

    admin = _admin(tmp_path, gateway, OLD_MASTER, transport=httpx.MockTransport(odd))
    await admin.start()  # never raises
    for _ in range(300):
        if engine_key(OLD_MASTER, "gemini") in gateway.virtual_keys():
            break
        await asyncio.sleep(0.01)
    assert engine_key(OLD_MASTER, "gemini") in gateway.virtual_keys()
    await admin.close()


@pytest.mark.parametrize("bad", ["", "   "])
async def test_an_empty_master_key_derives_no_engine_key(bad: str) -> None:
    """From an empty master key anyone could derive every engine's key, so none is made."""
    with pytest.raises(ValueError, match="master key"):
        engine_key(bad, "gemini")
    gateway = GatewayAdmin(httpx.AsyncClient(transport=_gateway().transport()), master=bad)
    with pytest.raises(ModelAdminRefused, match="master key is not set"):
        await gateway.put_engine_key(ModelProviderConfig.model_validate(GEMINI), EngineLimits())


def test_a_hosted_engine_named_local_is_refused() -> None:
    """`local` is the deployment's own engine (`schemas.deployment.LOCAL_ENGINE`); a hosted one of
    that name would be confused with it in every default and every tag."""
    with pytest.raises(ValueError, match="local"):
        ModelProviderConfig.model_validate({**GEMINI, "name": "local"})


async def test_test_the_connection_is_tagged_as_the_engine_s_test_job(tmp_path: Path) -> None:
    gateway = _gateway()
    admin = _admin(tmp_path, gateway, OLD_MASTER)
    await admin.add_engine("admin-1", ModelProviderConfig.model_validate(GEMINI))
    await admin.set_key("admin-1", "gemini", SecretStr(GOOD))
    await admin.test("admin-1", "gemini")
    tags = [body.get("metadata", {}).get("tags") for _token, body in gateway.received]
    assert tags == [["osprey:gemini/test"]]
