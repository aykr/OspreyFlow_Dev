"""*Admin › Models*: an edit that moves an engine's address and fails after its key is in the
gateway (AD1a's verifier, round 1; ADR-135 Amendment 14 decision 1: a key entered for one address is
never sent to another).

The check at the new address passes, the new key becomes the engine's credential, and then the
gateway refuses the entries or the models file cannot be written. The change is put back as the file
says, at the **old** address, and the engine's credential must not be the key typed for the new one:
the next analyst call would send it to the old address. The old key was replaced and cannot be
restored (a key is write-only), so the engine's key is recorded lost and entered again.

The case that catches it (rule 12):
`test_a_failed_moved_edit_never_leaves_the_new_key_at_the_old_address`, once for each way the
change can fail after the key is held.

**Round 3: the same rule holds while the edit succeeds.** The new key becomes the engine's
credential before the entries are rebuilt, and an entry names its credential, so for that moment
the old address's entries would carry the new key to the old address. An analyst call is not held
by the edit's lock, so
`test_a_moved_edit_never_sends_the_new_key_to_the_old_address_even_while_it_is_made` makes a call
at that very point (by wrapping `_reconcile`) and says where the gateway sent each key.

**Round 4: the same rule holds when the gateway's answer to the new key is lost.** A read timeout
or a dropped connection after the gateway stored the credential is read as "not stored", yet the
key is held and the edit then puts the engine back at the old address.
`test_a_new_key_whose_answer_is_lost_is_never_left_at_the_old_address` makes exactly that call (the
real store, then the words `_call` gives a transport failure). And a moved edit takes only its own
engine's entries away while it is made, not those of an engine whose name it begins:
`test_a_moved_edit_leaves_the_entries_of_an_engine_it_prefixes_in_place`.

**Round 5: the same rule holds when the gateway then refuses to remove the new key.** The undo
cannot take the key away, so the credential may still hold it and the old address's entries must not
be rebuilt on it. `test_a_new_key_the_gateway_will_not_remove_is_never_put_behind_the_old_address`
refuses `DELETE /credentials` as the real gateway can, then asserts the old address has no entry, a
later model-only edit sends nothing to the old address, and the refusal and its audit record say in
words that the key may still be held.

Keys are made at run time (the owner's rules for keys): none is written in this file.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_principal
from services.api.model_admin import ModelAdminRefused

from adapters.model_litellm.stand_in import StandInProvider
from tests.services.api.test_model_admin_routes import ADMIN, World

CHECKS = "/v1/admin/models/checks"
ENGINES = "/v1/admin/models/engines"
ENGINE = {"name": "gemini", "label": "Google Gemini", "roles": {"extraction": "gemini-2.5-flash"}}
OLD = "https://old-gateway.example.org/v1"
NEW = "https://proxy.example.org/v1"
MODELS = frozenset({"gemini-2.5-flash"})


def _a_key() -> str:
    return "sk-" + secrets.token_hex(16)


@pytest.fixture
def world(tmp_path: Path) -> Any:
    w = World(tmp_path)
    w.first = _a_key()
    w.second = _a_key()
    w.gateway.providers = {"gemini": StandInProvider(w.first, MODELS)}
    w.admin = w.make_admin()
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    app.state.model_admin = None


@pytest.fixture
def client(world: Any) -> TestClient:
    return TestClient(app)


def _add_at_the_old_address(client: TestClient, world: Any) -> None:
    check = client.post(
        CHECKS, json={"provider": {**ENGINE, "api_base": OLD}, "key": world.first}
    ).json()
    assert check["ok"], check
    added = client.post(f"{CHECKS}/{check['check']}/add")
    assert added.status_code == 200, added.text
    assert world.gateway.credential("osprey-gemini") == world.first


def _break(world: Any, how: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The change fails once, after the key is held; whatever puts the gateway back then works."""
    if how == "gateway refuses the entries":
        real = world.admin._reconcile
        failed: list[bool] = []

        async def refuse(*args: Any, **kwargs: Any) -> None:
            if not failed:
                failed.append(True)
                raise ModelAdminRefused("The model gateway refused the entry.", status=502)
            await real(*args, **kwargs)

        monkeypatch.setattr(world.admin, "_reconcile", refuse)
    else:
        def full(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("no space left on device")

        monkeypatch.setattr(world.admin._file, "save", full)


@pytest.mark.parametrize("how", ["gateway refuses the entries", "models file cannot be written"])
def test_a_failed_moved_edit_never_leaves_the_new_key_at_the_old_address(
    client: TestClient, world: Any, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    _add_at_the_old_address(client, world)
    world.gateway.providers = {"gemini": StandInProvider(world.second, MODELS)}
    _break(world, how, monkeypatch)
    moved = {**ENGINE, "api_base": NEW}
    refused = client.put(ENGINES + "/gemini", json={"provider": moved, "key": world.second})
    assert refused.status_code in (500, 502), refused.text
    assert world.second not in refused.text
    assert world.gateway.credential("osprey-gemini") != world.second, "the new key is held"
    assert world.gateway.credential("osprey-gemini") is None, "no key at all, not a stale one"
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert entry and world.gateway.stored_params(entry)["api_base"] == OLD, "put back at the old"
    monkeypatch.undo()
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] != "set", "not offered with no key behind it"
    assert not any(c for c in world.gateway._creds if ".check" in c), "no check credential left"


def test_a_moved_edit_never_sends_the_new_key_to_the_old_address_even_while_it_is_made(
    client: TestClient, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An analyst's call lands between the new key becoming the credential and the entries being
    rebuilt (the edit holds a lock the call does not take). Whatever answers it, the gateway must
    not have sent the new key to the old address; the engine may be briefly unavailable instead."""
    _add_at_the_old_address(client, world)
    world.gateway.providers = {"gemini": StandInProvider(world.second, MODELS)}
    real = world.admin._reconcile
    called: list[int] = []

    async def a_call_first(*args: Any, **kwargs: Any) -> None:
        if not called:
            http = world.admin._gateway.http
            answer = await http.post(
                "/chat/completions",
                json={
                    "model": "gemini/gemini-2.5-flash",
                    "messages": [{"role": "user", "content": "x"}],
                },
            )
            called.append(answer.status_code)
        await real(*args, **kwargs)

    monkeypatch.setattr(world.admin, "_reconcile", a_call_first)
    moved = {**ENGINE, "api_base": NEW}
    done = client.put(ENGINES + "/gemini", json={"provider": moved, "key": world.second})
    assert done.status_code == 200, done.text
    assert called, "the call was made between the key and the rebuild"
    assert (OLD, world.second) not in world.gateway.sent, "the new key went to the old address"
    assert (NEW, world.second) in world.gateway.sent, "checked at the new address"
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert entry and world.gateway.stored_params(entry)["api_base"] == NEW
    assert world.gateway.credential("osprey-gemini") == world.second


def test_a_new_key_whose_answer_is_lost_is_never_left_at_the_old_address(
    client: TestClient, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gateway stores the new key and the answer is lost (the words `_call` gives any transport
    failure). The edit cannot tell whether the key is held, so it takes the safe answer: the
    credential is removed and the engine's key is lost, never kept for the old address."""
    _add_at_the_old_address(client, world)
    world.gateway.providers = {"gemini": StandInProvider(world.second, MODELS)}
    gateway = world.admin._gateway
    real = gateway._call

    async def lost_answer(method: str, path: str, body: object | None = None) -> Any:
        answer = await real(method, path, body)
        if method == "POST" and path == "/credentials" and ".check" not in str(body):
            raise ModelAdminRefused(
                "The model gateway could not be reached; the change was not saved.", status=502
            )
        return answer

    monkeypatch.setattr(gateway, "_call", lost_answer)
    moved = {**ENGINE, "api_base": NEW}
    refused = client.put(ENGINES + "/gemini", json={"provider": moved, "key": world.second})
    assert refused.status_code in (500, 502), refused.text
    assert world.second not in refused.text
    assert world.gateway.credential("osprey-gemini") != world.second, "the new key is held"
    assert world.gateway.credential("osprey-gemini") is None, "no key at all, not a stale one"
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert entry and world.gateway.stored_params(entry)["api_base"] == OLD, "put back at the old"
    monkeypatch.undo()
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] != "set", "not offered with no key behind it"


def test_a_new_key_the_gateway_will_not_remove_is_never_put_behind_the_old_address(
    client: TestClient, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The moved edit fails once its key is held (the entries are refused), and the gateway then
    refuses to remove that key: it may still be the engine's credential. The undo must not make
    the old address's entries on it; the engine is unavailable and the person and the audit are
    told, in words, that the key may still be held."""
    _add_at_the_old_address(client, world)
    world.gateway.providers = {"gemini": StandInProvider(world.second, MODELS | {"gemini-2.5-pro"})}
    real = world.admin._reconcile
    failed: list[bool] = []

    async def refuse_once(*args: Any, **kwargs: Any) -> None:
        if not failed:
            failed.append(True)
            raise ModelAdminRefused("The model gateway refused the entry.", status=502)
        await real(*args, **kwargs)

    gateway = world.admin._gateway
    real_delete = gateway.delete_credential

    async def refuse_the_new_key_s_removal(provider: str) -> None:
        if provider == "gemini" and world.gateway.credential("osprey-gemini") == world.second:
            raise ModelAdminRefused("The model gateway refused the key's removal.", status=502)
        await real_delete(provider)

    monkeypatch.setattr(world.admin, "_reconcile", refuse_once)
    monkeypatch.setattr(gateway, "delete_credential", refuse_the_new_key_s_removal)
    moved = {**ENGINE, "api_base": NEW}
    refused = client.put(ENGINES + "/gemini", json={"provider": moved, "key": world.second})
    assert refused.status_code in (500, 502), refused.text
    assert world.second not in refused.text
    assert "may still be held" in refused.json()["detail"], "the person is told, in words"
    assert world.gateway.credential("osprey-gemini") == world.second, "the stand-in refused"
    assert not any(i.startswith("osprey-gemini-") for i in world.gateway.stored_ids()), (
        "an entry was rebuilt at the old address on a credential that may hold the new key"
    )
    audit = json.dumps([e.model_dump(mode="json") for e in world.audit.entries])
    assert "may still be held" in world.audit.entries[-1].outcome, "the audit says it"
    assert world.second not in audit, "the audit never holds the key"
    monkeypatch.undo()
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] == "lost", "not offered while the key may be held"
    # A later edit of a model name alone has no key and is not moved: its check must not use the
    # engine's credential, at the old address, with the new key behind it.
    world.gateway.sent.clear()
    again = client.put(
        ENGINES + "/gemini",
        json={"provider": {**ENGINE, "api_base": OLD, "roles": {"extraction": "gemini-2.5-pro"}}},
    )
    assert again.status_code in (409, 422), again.text
    assert (OLD, world.second) not in world.gateway.sent, "the new key went to the old address"


def test_a_moved_edit_leaves_the_entries_of_an_engine_it_prefixes_in_place(
    client: TestClient, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`gemini_pro` begins with `gemini`. While `gemini`'s entries are rebuilt, the neighbour's must
    stay in the gateway: `_reconcile` makes any missing one again afterwards, so a final-state check
    cannot tell, and this one looks at the very moment of the rebuild. It fails if the withdrawal
    matches `osprey-gemini` and not `osprey-gemini-`."""
    _add_at_the_old_address(client, world)
    world.gateway.providers["gemini_pro"] = StandInProvider(world.first, MODELS)
    pro = {"name": "gemini_pro", "label": "Gemini Pro", "roles": {"extraction": "gemini-2.5-flash"}}
    check = client.post(
        CHECKS, json={"provider": {**pro, "api_base": OLD}, "key": world.first}
    ).json()
    assert check["ok"], check
    assert client.post(f"{CHECKS}/{check['check']}/add").status_code == 200
    neighbour = {i for i in world.gateway.stored_ids() if i.startswith("osprey-gemini_pro-")}
    assert neighbour, "the neighbour has entries to lose"
    world.gateway.providers["gemini"] = StandInProvider(world.second, MODELS)
    real = world.admin._reconcile
    seen: list[set[str]] = []

    async def look_first(*args: Any, **kwargs: Any) -> None:
        if not seen:
            seen.append(set(world.gateway.stored_ids()))
        await real(*args, **kwargs)

    monkeypatch.setattr(world.admin, "_reconcile", look_first)
    moved = {**ENGINE, "api_base": NEW}
    done = client.put(ENGINES + "/gemini", json={"provider": moved, "key": world.second})
    assert done.status_code == 200, done.text
    assert seen, "the rebuild was reached"
    assert neighbour <= seen[0], "the neighbour's entries were taken away during the edit"
    assert not any(i.startswith("osprey-gemini-") for i in seen[0]), "gemini's own were kept"


def test_an_engine_name_with_a_hyphen_is_refused_so_the_withdrawal_prefix_is_exact(
    client: TestClient, world: Any
) -> None:
    """`_withdraw_entries` takes the entries named `osprey-<name>-`. That is one engine's own only
    while no engine's name can contain a hyphen (`gemini` and `gemini-pro` would share a prefix), so
    the name rule is what the prefix rests on: relaxing it must fail here first."""
    refused = client.post(
        CHECKS,
        json={"provider": {**ENGINE, "name": "gemini-pro", "api_base": OLD}, "key": world.first},
    )
    assert refused.status_code in (400, 422), refused.text
    assert "provider.name" in refused.text
