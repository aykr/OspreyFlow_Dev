"""*Admin › Models*' routes (`06_DECISIONS.md` ADR-135 Amendment 2, ADR-112 Amendment 7),
through the real app, the real right check and the real logger, against the stand-in gateway that
refuses as the pinned LiteLLM was measured to (rule 15;
`tests/adapters/model_litellm/test_stand_in_gateway.py`).

- rule 4: every `/v1/admin/models` route refuses a principal without `manage_models`, an
  administrator holding every other administration right included;
- the key: a recognisable planted key, sent through each real key route (and a malformed body, an
  unknown engine, and a connection test the stand-in answers by echoing part of it), appears in no
  response, log record, audit entry, models file or gateway row in plaintext;
- the round trip: after a write the engine's credential holds the key and each model entry names
  it; after a removal there is none; the Conduit never reads credentials back;
- the models file replaces `osprey.yaml`'s engines whole, is `600`, and refuses an engine beside
  `local_only: true`; a key the gateway lost (another encryption key) is shown "lost";
- routing follows a change with no restart.
"""

from __future__ import annotations

import json
import logging
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api.app import app, get_principal
from services.api.model_admin import (
    GatewayAdmin,
    InMemoryModelAdminAudit,
    Installed,
    ModelAdmin,
    ModelAdminRefused,
    ModelSettingsFile,
)

from adapters.model_litellm.stand_in import StandInGateway, StandInProvider
from schemas.deployment import ModelProviderConfig
from schemas.domain import Principal

MASTER = "sk-stand-in-master"
GOOD = "sk-good-provider-key-for-tests"
PLANTED = "sk-PLANTED-model-key-Q7Z4-do-not-leak"

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="u", roles=["osprey-admin"])
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="u", roles=["analyst"])
#: Every administration right but this one, granted singly.
EVERY_OTHER_ADMIN_RIGHT = Principal(
    id="admin-2",
    clearance="OFFICIAL",
    org_unit="u",
    roles=[
        f"right:{r}"
        for r in ("administer_system", "manage_people", "manage_geospatial", "read_audit")
    ],
)
MODELS_ONLY = Principal(id="m-1", clearance="OFFICIAL", org_unit="u", roles=["right:manage_models"])

GEMINI = {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini-2.5-flash"}}


def _installed(
    *, local_only: bool = False, providers: list[ModelProviderConfig] | None = None
) -> Installed:
    return Installed(
        providers=providers or [],
        defaults={},
        key_present={},
        local_only=local_only,
        sendable=["O"],
        locals={"extraction": "qwen2.5:7b-instruct", "vision": None, "transcription": None,
                "embedding": "all-minilm:22m-l6-v2-fp16"},
    )  # fmt: skip


class World:
    def __init__(self, tmp_path: Path, *, local_only: bool = False,
                 providers: list[ModelProviderConfig] | None = None) -> None:  # fmt: skip
        self.folder = tmp_path / "model-settings"
        self.gateway = StandInGateway(
            master_key=MASTER,
            salt_key="salt-one",
            providers={
                "gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash", "gemini-2.5-pro"})),
                "openai": StandInProvider(GOOD, frozenset({"gpt-4o-mini"})),
            },
        )
        self.audit = InMemoryModelAdminAudit()
        self.installed = _installed(local_only=local_only, providers=providers)
        self.admin = self.make_admin()

    def make_admin(self) -> ModelAdmin:
        http = httpx.AsyncClient(base_url="http://litellm:4000", transport=self.gateway.transport(),
                                 headers={"Authorization": f"Bearer {MASTER}"})  # fmt: skip
        return ModelAdmin(
            installed=self.installed,
            settings_file=ModelSettingsFile(self.folder),
            gateway=GatewayAdmin(http),
            audit=self.audit,
        )


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    w = World(tmp_path)
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    app.state.model_admin = None


@pytest.fixture
def client(world: World) -> TestClient:
    return TestClient(app)


def add(client: TestClient, provider: dict[str, Any], key: str | None = GOOD) -> httpx.Response:
    """An engine added as the screen adds one, the only way there is (the owner's ruling 18):
    checked with its key (none for an IAM-role engine), then added from the check. A check refused,
    or one that did not pass, is answered as it came; else Add's answer."""
    try:
        keyless = ModelProviderConfig.model_validate(provider).keyless
    except ValueError:
        keyless = False
    body: dict[str, Any] = {"provider": provider}
    if key is not None and not keyless:
        body["key"] = key
    checked = client.post("/v1/admin/models/checks", json=body)
    if checked.status_code != 200 or not checked.json()["ok"]:
        return checked
    return client.post(f"/v1/admin/models/checks/{checked.json()['check']}/add")


async def added(
    admin: ModelAdmin,
    provider: dict[str, Any],
    key: str | None = GOOD,
    by: str = "admin-1",
) -> None:
    """`add`, on the `ModelAdmin` itself."""
    from pydantic import SecretStr

    engine = ModelProviderConfig.model_validate(provider)
    sent = None if engine.keyless or key is None else SecretStr(key)
    result = await admin.check(by, engine, sent)
    assert result.ok and result.check, result
    await admin.add_checked(by, result.check)


def _as(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal


def _models_routes() -> list[APIRoute]:
    return [
        r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/v1/admin/models")
    ]


def _call(client: TestClient, route: APIRoute) -> httpx.Response:
    method = sorted(route.methods)[0]
    path = route.path.replace("{name}", "gemini")
    return client.request(method, path, json={"provider": GEMINI})


# --- rule 4 ------------------------------------------------------------------------------------


def test_there_are_thirteen_models_routes() -> None:
    # P1's nine, ADR-135 Amendment 3's limits and usage, and Amendment 14's check, its Add and its
    # Cancel; P1's own add is gone (the owner's ruling 18: no engine is added unchecked).
    assert len(_models_routes()) == 13


@pytest.mark.parametrize(
    "principal",
    [ANALYST, EVERY_OTHER_ADMIN_RIGHT],
    ids=["analyst", "every-other-admin-right"],
)
def test_every_models_route_refuses_a_principal_without_manage_models(
    client: TestClient, world: World, principal: Principal
) -> None:
    _as(principal)
    answers = {r.path + " " + sorted(r.methods)[0]: _call(client, r) for r in _models_routes()}
    refused = {k: v.status_code for k, v in answers.items() if v.status_code != 403}
    assert refused == {}
    assert all(v.json()["detail"]["right"] == "manage_models" for v in answers.values())
    # Nothing reached the gateway at all: no completion, no key, no usage read.
    assert world.gateway.seen == [] and world.audit.entries == []


@pytest.mark.parametrize("principal", [ADMIN, MODELS_ONLY], ids=["administrator", "granted-singly"])
def test_the_administrator_and_a_single_grant_reach_every_models_route(
    client: TestClient, principal: Principal
) -> None:
    _as(principal)
    assert {r.path: _call(client, r).status_code for r in _models_routes()
            if _call(client, r).status_code == 403} == {}  # fmt: skip


# --- the key never leaks -----------------------------------------------------------------------


def test_a_planted_key_appears_in_no_response_log_audit_file_or_gateway_row(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    bodies: list[str] = []

    def send(method: str, path: str, **kw: Any) -> httpx.Response:
        response = client.request(method, path, **kw)
        bodies.append(f"{response.status_code} {response.text} {dict(response.headers)}")
        return response

    assert add(client, GEMINI).status_code == 200
    key = "/v1/admin/models/engines/gemini/key"
    # Checked first (ruling 19): the stand-in refuses it and echoes part of it, as the real provider
    # did, so it replaces nothing; twice, as a rotation would be.
    for _ in range(2):
        assert send("PUT", key, json={"key": PLANTED}).status_code == 422
    assert send("POST", "/v1/admin/models/engines/gemini/test").json()["outcome"] == "ok"
    assert (
        send("PUT", "/v1/admin/models/engines/nope/key", json={"key": PLANTED}).status_code == 404
    )
    for malformed in ({"key": PLANTED, "extra": 1}, {"key": PLANTED * 300}, {"secret": PLANTED}):
        assert send("PUT", key, json=malformed).status_code == 422
    assert send("PUT", key, content=b'{"key": "' + PLANTED.encode() + b'"').status_code == 422
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")
    assert send("DELETE", key).status_code == 200

    fragments = (PLANTED, PLANTED[:12], "Q7Z4", "leak")
    seen = {
        "responses": "\n".join(bodies),
        "logs": "\n".join(r.getMessage() + repr(r.args) for r in caplog.records),
        "audit": json.dumps([e.model_dump(mode="json") for e in world.audit.entries]),
        "models file": (world.folder / "models.yaml").read_text(),
        "gateway rows": "\n".join(world.gateway.raw_rows()),
    }
    leaked = {where: f for where, text in seen.items() for f in fragments if f in text}
    assert leaked == {}
    # And it did reach the gateway, so the test is not passing by sending nothing.
    assert any(PLANTED[-4:] in line and PLANTED[:6] in line for line in world.gateway.log)


# --- the round trip ----------------------------------------------------------------------------


def test_the_key_reaches_the_gateway_credential_and_a_removal_takes_it_away(
    client: TestClient, world: World
) -> None:
    add(client, GEMINI)
    client.put("/v1/admin/models/engines/gemini/key", json={"key": GOOD})
    assert world.gateway.credential("osprey-gemini") == GOOD
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert entry is not None
    assert world.gateway.stored_params(entry)["litellm_credential_name"] == "osprey-gemini"
    assert "api_key" not in world.gateway.stored_params(entry)
    assert client.post("/v1/admin/models/engines/gemini/test").json()["outcome"] == "ok"

    # A model added to a keyed engine answers with no key entered again.
    wider = {**GEMINI, "roles": {"extraction": "gemini-2.5-flash", "vision": "gemini-2.5-pro"}}
    assert (
        client.put("/v1/admin/models/engines/gemini", json={"provider": wider}).status_code == 200
    )
    assert world.gateway.entry_for("gemini/gemini-2.5-pro") is not None

    assert client.delete("/v1/admin/models/engines/gemini/key").status_code == 200
    assert world.gateway.credential("osprey-gemini") is None
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] == "none"
    assert world.gateway.credential_reads == 0


def test_routing_follows_a_change_with_no_restart(client: TestClient, world: World) -> None:
    def offered() -> list[str]:
        _as(ANALYST)
        names = [e["name"] for e in client.get("/v1/models/engines").json()["engines"]]
        _as(ADMIN)
        return names

    add(client, GEMINI)
    assert offered() == ["local", "gemini"]
    client.delete("/v1/admin/models/engines/gemini/key")
    assert offered() == ["local"]  # no key: not offered
    client.put("/v1/admin/models/engines/gemini/key", json={"key": GOOD})
    assert offered() == ["local", "gemini"]


# --- the models file, the refusals, the audit --------------------------------------------------


def test_the_models_file_replaces_osprey_yaml_s_engines_whole_and_is_600(tmp_path: Path) -> None:
    installed = [ModelProviderConfig(name="openai", roles={"extraction": "gpt-4o-mini"})]
    w = World(tmp_path, providers=installed)
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    try:
        client = TestClient(app)
        assert client.get("/v1/admin/models").json()["source"] == "osprey.yaml"
        client.delete("/v1/admin/models/engines/openai")
        add(client, GEMINI)
        view = client.get("/v1/admin/models").json()
        assert [e["provider"]["name"] for e in view["engines"]] == ["gemini"]
        assert view["source"] == "models file"
        mode = stat.S_IMODE((w.folder / "models.yaml").stat().st_mode)
        assert mode == 0o600
        assert ModelSettingsFile(w.folder).load() is not None
    finally:
        app.dependency_overrides.clear()
        app.state.model_admin = None


def test_an_engine_beside_local_only_true_is_refused_in_words(tmp_path: Path) -> None:
    w = World(tmp_path, local_only=True)
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    try:
        answer = add(TestClient(app), GEMINI)
    finally:
        app.dependency_overrides.clear()
        app.state.model_admin = None
    assert answer.status_code == 422
    assert "local_only: true" in answer.json()["detail"]["detail"]
    assert not (w.folder / "models.yaml").exists()
    assert w.audit.entries[-1].outcome.startswith("refused")


def test_removing_a_role_s_default_engine_is_refused_naming_the_role(
    client: TestClient,
) -> None:
    add(client, GEMINI)
    assert (
        client.put(
            "/v1/admin/models/defaults", json={"defaults": {"extraction": "gemini"}}
        ).status_code
        == 200
    )
    answer = client.delete("/v1/admin/models/engines/gemini")
    assert answer.status_code == 422 and "extraction" in answer.json()["detail"]["detail"]


def test_every_change_is_audited_with_who_and_what(client: TestClient, world: World) -> None:
    add(client, GEMINI)
    client.put(
        "/v1/admin/models/engines/gemini",
        json={"provider": {**GEMINI, "label": "Google"}},
    )
    client.put("/v1/admin/models/engines/gemini/key", json={"key": GOOD})
    client.put("/v1/admin/models/defaults", json={"defaults": {"extraction": "gemini"}})
    client.post("/v1/admin/models/engines/gemini/test")
    client.put("/v1/admin/models/defaults", json={"defaults": {}})
    client.delete("/v1/admin/models/engines/gemini/key")
    client.delete("/v1/admin/models/engines/gemini")
    history = client.get("/v1/admin/models/history").json()["entries"]
    assert [e["action"] for e in reversed(history)] == [
        "engine_checked", "engine_added", "key_set", "engine_edited", "key_rotated",
        "default_changed", "connection_tested", "default_changed", "key_removed", "engine_removed",
    ]  # fmt: skip
    assert {e["by"] for e in history} == {"admin-1"}
    edited = next(e for e in history if e["action"] == "engine_edited")
    assert edited["changes"] == {"label": {"from": "Gemini", "to": "Google"}}


async def test_a_key_the_gateway_lost_is_shown_lost_and_not_offered(tmp_path: Path) -> None:
    w = World(tmp_path)
    await added(w.admin, GEMINI)
    from pydantic import SecretStr

    await w.admin.set_key("admin-1", "gemini", SecretStr(GOOD))
    w.gateway.restart(salt_key="salt-two")  # a restore onto another deployment
    again = w.make_admin()
    await again.start()
    assert again.key_state("gemini") == "lost"
    assert not again.routes().engines["gemini"].key_present


async def test_moving_keys_from_deployment_env_puts_each_in_the_gateway(tmp_path: Path) -> None:
    """Each key of an enabled engine is moved; a key for an engine no longer enabled (removed in
    Admin › Models) is dropped and named, so every apply after does not fail on it."""
    from services.api.model_keys import move_keys

    w = World(tmp_path, providers=[ModelProviderConfig.model_validate(GEMINI)])
    moved, skipped = await move_keys(w.admin, [f"GEMINI={GOOD}", "OPENAI=sk-x"], "cli:ayan")
    assert (moved, skipped) == (["gemini"], ["openai"])
    assert w.gateway.credential("osprey-gemini") == GOOD
    assert w.admin.key_state("gemini") == "set"
    assert [e.action for e in w.audit.entries][-1] == "key_moved"
    assert GOOD not in (w.folder / "models.yaml").read_text()


async def test_a_second_conduit_replica_follows_a_change_made_through_the_first(
    tmp_path: Path,
) -> None:
    """Enterprise runs several Conduit replicas on one shared models file (`harness/cluster.py`):
    each reads it again when it changes, so routing agrees whichever replica the analyst reaches."""
    import os

    from pydantic import SecretStr

    w = World(tmp_path)
    other = w.make_admin()
    await added(w.admin, GEMINI)
    await w.admin.set_key("admin-1", "gemini", SecretStr(GOOD))
    path = w.folder / "models.yaml"
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
    assert other.key_state("gemini") == "set"
    assert other.routes().engines["gemini"].key_present


# --- found by the lane's own review (8 November 2026) ------------------------------------------


def test_no_route_echoes_a_key_shaped_value_in_a_refusal(client: TestClient) -> None:
    """`contract_reference` refuses a value shaped like a key; FastAPI's own 422 would send it
    back. Every Models route reads its own body, so the refusal names the field, never the value."""
    shaped = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd"
    for method, path in (
        ("POST", "/v1/admin/models/checks"),
        ("PUT", "/v1/admin/models/engines/gemini"),
    ):
        contracted = {**GEMINI, "privacy_contract": True, "contract_reference": shaped}
        answer = client.request(method, path, json={"provider": contracted, "key": GOOD})
        assert answer.status_code == 422, answer.text
        assert shaped not in answer.text and "contract_reference" in answer.text
    answer = client.put("/v1/admin/models/defaults", json={"defaults": [shaped]})
    assert answer.status_code == 422 and shaped not in answer.text


def test_a_lost_key_is_lost_for_every_process_and_entering_it_again_clears_it(
    tmp_path: Path,
) -> None:
    import asyncio

    from pydantic import SecretStr

    w = World(tmp_path)
    asyncio.run(added(w.admin, GEMINI))
    asyncio.run(w.admin.set_key("admin-1", "gemini", SecretStr(GOOD)))
    w.gateway.restart(salt_key="salt-two")  # a restore onto another deployment
    first = w.make_admin()
    asyncio.run(first.start())  # makes the entries again, and records the loss
    second = w.make_admin()  # another replica, or the command line, after the first start
    asyncio.run(second.start())
    assert first.key_state("gemini") == second.key_state("gemini") == "lost"
    assert first.view().engines[0].key_state == "lost"
    asyncio.run(second.set_key("cli:ayan", "gemini", SecretStr(GOOD)))
    assert first.key_state("gemini") == "set"  # the running Conduit follows the file
    assert w.gateway.credential("osprey-gemini") == GOOD
    assert w.gateway.patches == []


def test_a_gateway_that_refuses_leaves_the_models_file_and_routing_as_they_were(
    client: TestClient, world: World
) -> None:
    add(client, GEMINI)
    before = (world.folder / "models.yaml").read_text()
    world.gateway.master_key = "rotated-elsewhere"  # every admin call now refused
    answer = client.put("/v1/admin/models/engines/gemini",
                        json={"provider": {**GEMINI, "label": "Changed"}})  # fmt: skip
    assert answer.status_code == 502 and "not saved" in answer.json()["detail"]["detail"]
    assert (world.folder / "models.yaml").read_text() == before
    world.gateway.master_key = MASTER
    assert client.get("/v1/admin/models").json()["engines"][0]["provider"]["label"] == "Gemini"


def test_clearing_an_engine_s_address_leaves_nothing_of_the_old_one(
    client: TestClient, world: World
) -> None:
    based = {**GEMINI, "api_base": "https://proxy.example.org/v1"}
    add(client, based)
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert (
        entry and world.gateway.stored_params(entry)["api_base"] == "https://proxy.example.org/v1"
    )
    # A cleared address is a changed one: its key goes with it (the owner's ruling 19).
    client.put("/v1/admin/models/engines/gemini", json={"provider": GEMINI, "key": GOOD})
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert entry and "api_base" not in world.gateway.stored_params(entry)
    assert world.gateway.patches == []


def test_engines_in_the_models_file_are_not_offered_while_osprey_yaml_says_local_only(
    tmp_path: Path,
) -> None:
    import asyncio

    from pydantic import SecretStr

    w = World(tmp_path)
    asyncio.run(added(w.admin, GEMINI))
    asyncio.run(w.admin.set_key("admin-1", "gemini", SecretStr(GOOD)))
    w.installed = _installed(local_only=True)  # the installer declared local only since
    assert w.make_admin().routes().engines == {}


# --- found by the independent review (8 November 2026) -----------------------------------------

KEY_SHAPED = "sk-proj-Zq81-PLANTED key-shaped value"


def test_an_address_changed_without_its_key_is_refused_and_the_old_key_goes_nowhere_new(
    client: TestClient, world: World
) -> None:
    """The owner's ruling (decision 1): the address decides where the key is sent, so a key entered
    for one address is never sent to another. Since ruling 19 a changed address takes its key with
    it, checked there; without one the edit is refused and the engine keeps its address and key."""
    add(client, GEMINI)
    elsewhere = {**GEMINI, "api_base": "https://collector.example.net/v1"}
    answer = client.put("/v1/admin/models/engines/gemini", json={"provider": elsewhere})
    assert answer.status_code == 422 and "give its key with it" in answer.json()["detail"]["detail"]
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] == "set"
    assert view["engines"][0]["provider"]["api_base"] is None
    assert world.gateway.credential("osprey-gemini") == GOOD
    assert all(not (base and "collector" in base) for base, _key in world.gateway.sent)


def test_a_new_key_the_gateway_will_not_store_replaces_nothing(
    client: TestClient, world: World
) -> None:
    """Ruling 19's check holds the new key as its own credential first: a gateway that stores no
    credential refuses there, and the engine keeps its key, still offered."""
    add(client, GEMINI)
    world.gateway.refuse_credentials = 500
    answer = client.put("/v1/admin/models/engines/gemini/key", json={"key": "sk-new-but-refused"})
    assert answer.status_code == 502 and "nothing was changed" in answer.json()["detail"]["detail"]
    assert client.get("/v1/admin/models").json()["engines"][0]["key_state"] == "set"
    assert world.gateway.credential("osprey-gemini") == GOOD
    assert world.admin.routes().engines["gemini"].key_present is True


def test_a_checked_key_the_gateway_then_refuses_is_recorded_as_lost_and_not_offered(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check passed, the old key was removed, and the gateway refused the new one under the
    engine's own name: the engine's key is then lost, recorded so and offered to no analyst."""
    from services.api.model_admin import KeyRemovedNotReplaced

    add(client, GEMINI)
    gateway = world.admin._gateway  # noqa: SLF001
    put = gateway.put_credential

    async def refused_for_the_engine(provider: str, key: Any) -> None:
        if provider != "gemini":
            return await put(provider, key)
        await gateway.delete_credential(provider)
        raise KeyRemovedNotReplaced(
            "The model gateway refused the new key (HTTP 500) after the old one was removed: the "
            "engine has no key now and is offered to no analyst.",
            status=502,
        )

    monkeypatch.setattr(gateway, "put_credential", refused_for_the_engine)
    answer = client.put("/v1/admin/models/engines/gemini/key", json={"key": GOOD})
    assert answer.status_code == 502 and "has no key now" in answer.json()["detail"]["detail"]
    assert client.get("/v1/admin/models").json()["engines"][0]["key_state"] == "lost"
    assert world.admin.routes().engines["gemini"].key_present is False


def test_a_refusal_names_the_field_never_the_value_in_the_answer_or_the_audit(
    client: TestClient, world: World
) -> None:
    bad_roles = {**GEMINI, "roles": {"extraction": KEY_SHAPED}}
    bad_name = {**GEMINI, "name": KEY_SHAPED}
    answers = [
        add(client, bad_roles),
        add(client, bad_name),
        client.put("/v1/admin/models/defaults", json={"defaults": {"extraction": KEY_SHAPED}}),
    ]
    assert [a.status_code for a in answers] == [422, 422, 422]
    shown = " ".join(a.text for a in answers) + json.dumps(
        [e.model_dump(mode="json") for e in world.audit.entries]
    )
    assert KEY_SHAPED not in shown and "PLANTED" not in shown
    assert "roles" in answers[0].text


def test_a_change_that_fails_part_way_puts_the_gateway_back_and_saves_nothing(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(client, GEMINI)
    before = (world.folder / "models.yaml").read_text()
    made = world.admin._gateway.add_entry  # noqa: SLF001
    calls = {"n": 0}

    async def refused_once(provider: ModelProviderConfig, model: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelAdminRefused("The model gateway refused the model (HTTP 500).", status=502)
        await made(provider, model)

    monkeypatch.setattr(world.admin._gateway, "add_entry", refused_once)  # noqa: SLF001
    answer = client.put("/v1/admin/models/engines/gemini",
                        json={"provider": {**GEMINI, "label": "Changed"}})  # fmt: skip
    assert answer.status_code == 502
    assert (world.folder / "models.yaml").read_text() == before
    assert world.gateway.entry_for("gemini/gemini-2.5-flash") is not None  # put back
    assert world.audit.entries[-1].outcome.startswith("refused")


def test_a_models_file_that_cannot_be_written_is_a_refusal_audited_with_the_gateway_put_back(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(client, GEMINI)

    def full(_settings: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(world.admin._file, "save", full)  # noqa: SLF001
    answer = add(client, {"name": "openai", "roles": {"extraction": "gpt-4o-mini"}})
    assert answer.status_code == 500 and "not saved" in answer.json()["detail"]["detail"]
    assert world.gateway.entry_for("openai/gpt-4o-mini") is None
    # The check's key is not left in the gateway with nothing on record to remove it.
    assert world.gateway.credential("osprey-openai") is None
    assert world.audit.entries[-1].outcome.startswith("refused")


def test_two_changes_at_once_from_two_processes_both_land(tmp_path: Path) -> None:
    """Two administrators, two replicas or the CLI: each change holds the models file's lock and
    reads it afresh, so neither writes over the other."""
    import asyncio

    w = World(tmp_path)
    other = w.make_admin()
    for admin in (w.admin, other):  # a slow gateway, so the two changes overlap
        # The listing every change reads between reading the file and saving it (`_reconcile`
        # reads it with `held_entries`; `stored_entries` is a wrapper nothing in a change calls).
        listed = admin._gateway.held_entries  # noqa: SLF001

        async def slow(listed: Any = listed) -> Any:
            await asyncio.sleep(0.05)
            return await listed()

        admin._gateway.held_entries = slow  # type: ignore[method-assign]  # noqa: SLF001

    async def both() -> None:
        await asyncio.gather(
            added(w.admin, GEMINI),
            added(
                other,
                {"name": "openai", "roles": {"extraction": "gpt-4o-mini"}},
                by="admin-2",
            ),
        )

    asyncio.run(both())
    names = sorted(p.name for p in ModelSettingsFile(w.folder).load().providers)  # type: ignore[union-attr]
    assert names == ["gemini", "openai"]


def test_a_key_with_spaces_or_only_spaces_is_refused(client: TestClient) -> None:
    add(client, GEMINI)
    for key in ("   ", "sk-has a space"):
        answer = client.put("/v1/admin/models/engines/gemini/key", json={"key": key})
        assert answer.status_code == 422 and "no spaces" in answer.json()["detail"]["detail"]


def test_a_local_only_deployment_keeps_no_hosted_entry_and_asks_no_engine(tmp_path: Path) -> None:
    import asyncio

    w = World(tmp_path)
    asyncio.run(added(w.admin, GEMINI))
    w.installed = _installed(local_only=True)
    w.gateway.asked.clear()  # the check before Add asked once; nothing may be asked from here
    local = w.make_admin()
    asyncio.run(local.start())
    assert w.gateway.stored_ids() == set()
    result = asyncio.run(local.test("admin-1", "gemini"))
    assert not result.ok and "local only" in result.words
    assert w.gateway.asked == []
    asyncio.run(local.remove_engine("admin-1", "gemini"))  # narrowing is always allowed
    assert local.view().engines == []
