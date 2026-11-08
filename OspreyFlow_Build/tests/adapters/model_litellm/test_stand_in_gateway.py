"""The stand-in gateway refuses as the measured one does (`CLAUDE.md` rule 15; `06_DECISIONS.md`
ADR-135 Amendment 2, "Measured first"). No test against the stand-in is trusted until each refusal
here has been seen; each case is the request shape the Conduit's own code sends.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from adapters.model_litellm.stand_in import StandInGateway, StandInProvider

MASTER = "sk-stand-in-master"
GOOD = "sk-good-provider-key"
PLANTED = "sk-PLANTED-wrong-key-7Q4Z"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _gateway(clock: Clock | None = None) -> StandInGateway:
    return StandInGateway(
        master_key=MASTER,
        salt_key="salt-one",
        providers={"gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash"}))},
        config_models=frozenset({"qwen2.5:7b-instruct"}),
        clock=clock or Clock(),
    )


def _client(gateway: StandInGateway, token: str | None = MASTER) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        base_url="http://litellm:4000", transport=gateway.transport(), headers=headers
    )


def _entry(model_id: str, key: str | None, model: str = "gemini-2.5-flash") -> dict[str, Any]:
    params: dict[str, Any] = {"model": f"gemini/{model}"}
    if key is not None:
        params["api_key"] = key
    return {
        "model_name": f"gemini/{model}",
        "litellm_params": params,
        "model_info": {"id": model_id},
    }


async def _chat(client: httpx.AsyncClient, model: str) -> httpx.Response:
    return await client.post(
        "/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 1,
        },
    )


async def test_the_proxy_refuses_no_token_and_a_wrong_one_echoing_its_last_four() -> None:
    gateway = _gateway()
    async with _client(gateway, None) as client:
        none = await client.post("/model/new", json={})
    async with _client(gateway, "sk-wrong-master-XYZW") as client:
        wrong = await client.post("/model/new", json={})
    assert none.status_code == 401 and "No api key passed in" in none.text
    assert wrong.status_code == 401 and "proxy server token" in wrong.text
    assert "sk-...XYZW" in wrong.text


async def test_model_new_refuses_an_empty_body_and_a_duplicate_id_but_accepts_no_key() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        empty = await client.post("/model/new", json={})
        first = await client.post("/model/new", json=_entry("osprey-gemini-a", None))
        again = await client.post("/model/new", json=_entry("osprey-gemini-a", GOOD))
    assert empty.status_code == 500
    assert first.status_code == 200  # measured: accepted with no key
    assert again.status_code == 500 and "Failed to add model to db" in again.text


async def test_a_stored_key_is_never_plaintext_in_the_store_or_the_response() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        added = await client.post("/model/new", json=_entry("osprey-gemini-a", PLANTED))
    assert PLANTED not in added.text
    assert all(PLANTED not in row for row in gateway.raw_rows())
    assert gateway.stored_params("osprey-gemini-a")["api_key"] == PLANTED


async def test_update_and_delete_refuse_an_unknown_id_and_update_needs_model_info() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        patch = await client.patch(
            "/model/osprey-nope/update", json={"litellm_params": {"api_key": GOOD}}
        )
        post = await client.post("/model/update", json={"litellm_params": {"api_key": GOOD}})
        delete = await client.post("/model/delete", json={"id": "osprey-nope"})
    assert patch.status_code == 404 and "not found on proxy" in patch.text
    assert post.status_code == 400 and "model_info not provided" in post.text
    assert delete.status_code == 400 and "not found in db" in delete.text


async def test_completions_refuse_as_measured() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        for entry in (
            _entry("nokey", None),
            _entry("wrong", PLANTED, "gemini-2.5-pro"),
            _entry("notoffered", GOOD, "gemini-ultra"),
        ):
            entry["model_name"] = f"gemini/{entry['model_info']['id']}"
            assert (await client.post("/model/new", json=entry)).status_code == 200
        unknown = await _chat(client, "no/such-model")
        nokey = await _chat(client, "gemini/nokey")
        wrong = await _chat(client, "gemini/wrong")
        notoffered = await _chat(client, "gemini/notoffered")
        local = await _chat(client, "qwen2.5:7b-instruct")
    assert unknown.status_code == 400 and "Invalid model name" in unknown.text
    assert nokey.status_code == 500 and "AuthenticationError" in nokey.text
    assert wrong.status_code == 401 and "sk-PLA****7Q4Z" in wrong.text
    assert any("7Q4Z" in line for line in gateway.log)  # the gateway's own log carries it too
    assert notoffered.status_code == 404 and "NotFoundError" in notoffered.text
    assert local.status_code == 200


async def test_a_failure_cools_the_entry_down_even_after_a_good_key_is_set() -> None:
    clock = Clock()
    gateway = _gateway(clock)
    async with _client(gateway) as client:
        await client.post("/model/new", json=_entry("osprey-gemini-a", PLANTED))
        assert (await _chat(client, "gemini/gemini-2.5-flash")).status_code == 401
        await client.patch(
            "/model/osprey-gemini-a/update", json={"litellm_params": {"api_key": GOOD}}
        )
        cooled = await _chat(client, "gemini/gemini-2.5-flash")
        clock.now = 61.0
        after = await _chat(client, "gemini/gemini-2.5-flash")
    assert cooled.status_code == 429 and "cooldown_list" in cooled.text
    assert after.status_code == 200


async def test_a_deleted_entry_is_no_longer_routed() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        await client.post("/model/new", json=_entry("osprey-gemini-a", GOOD))
        assert (
            await client.post("/model/delete", json={"id": "osprey-gemini-a"})
        ).status_code == 200
        gone = await _chat(client, "gemini/gemini-2.5-flash")
    assert gone.status_code == 400 and "Invalid model name" in gone.text


@pytest.mark.parametrize("salt", ["salt-one", "salt-two"])
async def test_a_restart_keeps_entries_only_under_the_same_encryption_key(salt: str) -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        await client.post("/model/new", json=_entry("osprey-gemini-a", GOOD))
    gateway.restart(salt_key=salt)
    async with _client(gateway) as client:
        answer = await _chat(client, "gemini/gemini-2.5-flash")
        info = await client.get("/v2/model/info")
    if salt == "salt-one":
        assert answer.status_code == 200
        assert "osprey-gemini-a" in info.text and GOOD not in info.text
    else:
        assert answer.status_code == 400 and "Invalid model name" in answer.text
        assert "osprey-gemini-a" not in info.text


def _by_credential(model_id: str, model: str = "gemini-2.5-flash") -> dict[str, Any]:
    return {
        "model_name": f"gemini/{model}",
        "litellm_params": {"model": f"gemini/{model}", "litellm_credential_name": "osprey-gemini"},
        "model_info": {"id": model_id},
    }


async def test_a_credential_serves_every_entry_naming_it_and_its_rotation_reaches_them() -> None:
    gateway = _gateway()
    gateway.providers = {
        "gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash", "gemini-2.5-pro"}))
    }
    async with _client(gateway) as client:
        await client.post("/model/new", json=_by_credential("a"))
        missing = await _chat(client, "gemini/gemini-2.5-flash")  # names a credential not yet made
        gateway.restart()  # clear the cooldown the missing key caused
        await client.post(
            "/credentials",
            json={"credential_name": "osprey-gemini", "credential_values": {"api_key": PLANTED}},
        )
        wrong = await _chat(client, "gemini/gemini-2.5-flash")
        gateway.restart()
        rotated = await client.patch(
            "/credentials/osprey-gemini",
            json={"credential_name": "osprey-gemini", "credential_values": {"api_key": GOOD}},
        )
        await client.post("/model/new", json=_by_credential("b", "gemini-2.5-pro"))
        first = await _chat(client, "gemini/gemini-2.5-flash")
        second = await _chat(client, "gemini/gemini-2.5-pro")
        unknown = await client.delete("/credentials/osprey-nope")
        await client.delete("/credentials/osprey-gemini")
        gone = await _chat(client, "gemini/gemini-2.5-pro")
    assert missing.status_code == 500 and "AuthenticationError" in missing.text
    assert wrong.status_code == 401
    assert rotated.status_code == 200 and first.status_code == 200 and second.status_code == 200
    assert unknown.status_code == 404 and "Credential not found" in unknown.text
    assert gone.status_code == 500 and "AuthenticationError" in gone.text
    assert all(PLANTED not in row and GOOD not in row for row in gateway.raw_rows())


async def test_reading_credentials_back_returns_them_masked_and_is_counted() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        await client.post(
            "/credentials",
            json={"credential_name": "osprey-gemini", "credential_values": {"api_key": PLANTED}},
        )
        listed = await client.get("/credentials")
    assert "sk****4Z" in listed.text and PLANTED not in listed.text
    assert gateway.credential_reads == 1


async def test_a_different_encryption_key_drops_credentials_too() -> None:
    gateway = _gateway()
    async with _client(gateway) as client:
        await client.post(
            "/credentials",
            json={"credential_name": "osprey-gemini", "credential_values": {"api_key": GOOD}},
        )
    gateway.restart(salt_key="salt-two")
    assert gateway.credential("osprey-gemini") is None
