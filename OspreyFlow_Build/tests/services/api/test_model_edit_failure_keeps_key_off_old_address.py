"""*Admin › Models*: an edit that moves an engine's address and fails after its key is in the
gateway (AD1a's verifier, round 1; ADR-135 Amendment 14 decision 1: a key entered for one address is
never sent to another).

The check at the new address passes, the new key becomes the engine's credential, and then the
gateway refuses the entries or the models file cannot be written. The change is put back as the file
says, at the **old** address, and the engine's credential must not be the key typed for the new one:
the next analyst call would send it to the old address. The old key was replaced and cannot be
restored (a key is write-only), so the engine's key is recorded lost and entered again.

The case that catches it (rule 12): `test_a_failed_moved_edit_never_leaves_the_new_key_at_the_old_address`,
once for each way the change can fail after the key is held. Keys are made at run time (the owner's
rules for keys): none is written in this file.
"""

from __future__ import annotations

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


def _a_key() -> str:
    return "sk-" + secrets.token_hex(16)


@pytest.fixture
def world(tmp_path: Path) -> Any:
    w = World(tmp_path)
    w.first = _a_key()
    w.second = _a_key()
    w.gateway.providers = {"gemini": StandInProvider(w.first, frozenset({"gemini-2.5-flash"}))}
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
    world.gateway.providers = {"gemini": StandInProvider(world.second, frozenset({"gemini-2.5-flash"}))}
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
