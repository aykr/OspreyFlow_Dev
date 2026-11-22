"""Each engine's own gateway key (`06_DECISIONS.md` ADR-135 Amendment 3, "As built in P3"): it may
call its own engine's models and no other, and a gateway answering nonsense at start never stops the
Conduit starting. (A key the current master key would not derive was revoked at the next reconcile
from a listing of the gateway's keys until AD1a round 10: the listing answers `key_name`, part of each
key, so the owner ruled on 21 November 2026 that the Conduit asks for none: ADR-135 Amendment 14
point 9. What clears a stale key now is in `test_model_key_paths.py`'s N4 cases; a master key changed
is the open row N6.)

The gateway is the stand-in (`adapters.model_litellm.stand_in`), whose own proof of each measured
answer used here (a key's `models`, `/key/list`'s pages, a delete by hash) is
`tests/adapters/model_litellm/test_stand_in_gateway_usage.py`. Each case was shown red first
(`process/lanes/platform/P3_RED_RECORD.md`).
"""

from __future__ import annotations

import asyncio
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
from tests.services.api.test_model_admin_routes import added

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
            "gemini": StandInProvider(
                GOOD, frozenset({"gemini-2.5-flash", "gemini-2.5-pro"}), 17, 5
            ),
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
        await added(admin, engine, GOOD)
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


async def test_a_changed_master_key_makes_the_new_keys_and_asks_for_no_listing(
    tmp_path: Path,
) -> None:
    """After a master-key rotation the next start makes each engine's key under the new master, and
    **asks the gateway for no listing of keys** (`GET /key/list` answers `key_name`, part of each
    key; the owner's ruling, 21 November 2026), and so leaves every other key alone. The old
    engine keys are not named by anything the Conduit holds: see the strict `xfail` below, the
    open row N6."""
    gateway = _gateway()
    old = _admin(tmp_path, gateway, OLD_MASTER)
    for engine in (GEMINI, OPENAI):
        await added(old, engine, GOOD)
    async with httpx.AsyncClient(
        base_url="http://litellm:4000",
        transport=gateway.transport(),
        headers={"Authorization": f"Bearer {OLD_MASTER}"},
    ) as master:
        await master.post("/key/generate", json={"key": "sk-not-ours-0001",
                                                 "metadata": {"team": "x"}})  # fmt: skip
    gateway.master_key = NEW_MASTER  # the gateway restarted under a new master key
    mark = len(gateway.seen)
    new = _admin(tmp_path, gateway, NEW_MASTER)
    await new.start()
    held = set(gateway.virtual_keys())
    assert {engine_key(NEW_MASTER, "gemini"), engine_key(NEW_MASTER, "openai")} <= held
    assert "sk-not-ours-0001" in held
    asked = [line.split(" ")[1] for line in gateway.seen[mark:] if line.startswith("GET ")]
    assert not [p for p in asked if p.startswith(("/key/list", "/credentials"))]
    assert gateway.credential_reads == 0


@pytest.mark.xfail(
    strict=True,
    reason="open row N6 (AD1a round 10): a changed master key leaves the old derived engine keys "
    "valid, and no listing may be asked for to find them; this goes red (XPASS) when a route lands",
)
async def test_a_changed_master_key_revokes_the_old_engine_keys_n6(tmp_path: Path) -> None:
    gateway = _gateway()
    old = _admin(tmp_path, gateway, OLD_MASTER)
    for engine in (GEMINI, OPENAI):
        await added(old, engine, GOOD)
    old_keys = {engine_key(OLD_MASTER, "gemini"), engine_key(OLD_MASTER, "openai")}
    gateway.master_key = NEW_MASTER
    await _admin(tmp_path, gateway, NEW_MASTER).start()
    assert not old_keys & set(gateway.virtual_keys())


async def test_a_garbled_first_answer_never_stops_the_conduit_starting(tmp_path: Path) -> None:
    """A 200 that is not JSON on the very first reconcile: `start` returns, and the retry finishes
    the work once the gateway answers properly."""
    gateway = _gateway()
    await added(_admin(tmp_path, gateway, OLD_MASTER), GEMINI, GOOD)
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
    await added(admin, GEMINI, GOOD)
    await admin.set_key("admin-1", "gemini", SecretStr(GOOD))
    await admin.test("admin-1", "gemini")
    tags = [body.get("metadata", {}).get("tags") for _token, body in gateway.received]
    # The check before Add, the new key's check (ruling 19) and the test: each the engine's `test`.
    assert tags == [["osprey:gemini/test"]] * 3
