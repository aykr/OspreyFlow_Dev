"""*Admin › Models*' check before Add (the owner's prompt of 15 November 2026, pattern 3; ADR-135
Amendment 14 point 2, the first slice): the key and each typed model are proved by one call in the
gateway before the engine exists, and **Add** takes the check, never the key.

The flow, through the real app and the stand-in gateway that refuses as LiteLLM does (rule 15):
`POST /v1/admin/models/checks` takes the engine and its key once. The Conduit hands the key to the
gateway as the engine's own credential and keeps nothing, makes a passing entry for each typed model
that no route offers, asks each with today's one-token call (decision 5's fixed words), and removes
the entries. A passed check is held in the models file for 15 minutes; **Add**
(`POST …/checks/{id}/add`) makes the engine from it; **Cancel** (`DELETE …/checks/{id}`) or the 15
minutes removes the credential.

What a mistake would do, and the case that catches it (rule 12):
- an engine added unchecked: `test_add_is_refused_without_a_passed_check`;
- a refused key or model kept in the gateway:
  `test_a_refused_key_or_model_leaves_nothing_in_the_gateway`;
- a checked engine offered to analysts before Add: `test_a_passed_check_offers_nothing_until_add`;
- a check outliving its 15 minutes: `test_a_check_not_added_in_15_minutes_is_removed`;
- the key anywhere it must not be: `test_the_key_appears_nowhere_it_must_not`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.api.app import app, get_principal

from adapters.model_litellm.stand_in import StandInProvider
from tests.services.api.test_model_admin_routes import ADMIN, GOOD, World

CHECKS = "/v1/admin/models/checks"
PLANTED = "sk-PLANTED-check-key-W3R8-do-not-leak"
ENGINE = {"name": "gemini", "label": "Google Gemini", "roles": {"extraction": "gemini-2.5-flash"}}


class _Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def world(tmp_path: Path, clock: _Clock) -> Any:
    w = World(tmp_path)
    w.admin = w.make_admin()
    w.admin._now = clock  # the check's 15 minutes, on a clock the test moves
    app.state.model_admin = w.admin
    app.dependency_overrides[get_principal] = lambda: ADMIN
    yield w
    app.dependency_overrides.clear()
    app.state.model_admin = None


@pytest.fixture
def client(world: Any) -> TestClient:
    return TestClient(app)


def _check(client: TestClient, key: str | None = GOOD, **engine: Any) -> httpx.Response:
    body: dict[str, Any] = {"provider": {**ENGINE, **engine}}
    if key is not None:
        body["key"] = key
    return client.post(CHECKS, json=body)


def _credentials(world: Any) -> list[str]:
    """The credentials the gateway holds, by name (the stand-in's own store)."""
    return sorted(world.gateway._creds)


def _nowhere(
    world: Any,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
    seen: list[str],
    fragments: tuple[str, ...],
) -> dict[str, str]:
    """Where each fragment was found: the answers, every log record formatted whole (message, args,
    traceback, stack: P4), the process's own output (P4), the audit, every file under the test's
    folder, the lock and any temporary included (P5), and the gateway's rows."""
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    records = []
    for r in caplog.records:
        whole = formatter.format(r) + repr(r.args)
        records.append(whole + str(r.exc_text or "") + str(r.stack_info))
    out, err = capfd.readouterr()
    files = "\n".join(
        p.read_bytes().decode("utf-8", "replace") for p in tmp_path.rglob("*") if p.is_file()
    )
    where = {
        "answers": "\n".join(seen),
        "log records": "\n".join(records),
        "stdout and stderr": out + err,
        "audit": json.dumps([e.model_dump(mode="json") for e in world.audit.entries]),
        "files": files,
        "gateway rows": "\n".join(world.gateway.raw_rows()),
    }
    return {w: f for w, text in where.items() for f in fragments if f in text}


def test_a_good_key_and_model_pass_and_add_makes_the_engine_from_the_check(
    client: TestClient, world: Any
) -> None:
    checked = _check(client)
    assert checked.status_code == 200, checked.text
    answer = checked.json()
    assert answer["ok"] is True and answer["check"]
    assert [m["outcome"] for m in answer["models"]] == ["ok"]
    added = client.post(f"{CHECKS}/{answer['check']}/add")
    assert added.status_code == 200, added.text
    engine = next(e for e in added.json()["engines"] if e["provider"]["name"] == "gemini")
    assert engine["key_state"] == "set"
    assert world.gateway.entry_for("gemini/gemini-2.5-flash") is not None
    actions = [e.action for e in world.audit.entries]
    assert actions[:2] == ["engine_checked", "engine_added"] and "key_set" in actions


def test_a_passed_check_offers_nothing_until_add(client: TestClient, world: Any) -> None:
    assert _check(client).json()["ok"] is True
    view = client.get("/v1/admin/models").json()
    assert all(e["provider"]["name"] != "gemini" for e in view["engines"]), "not an engine yet"
    assert world.gateway.entry_for("gemini/gemini-2.5-flash") is None, "no entry left routable"
    assert world.gateway.stored_ids() == set(), "nor any under the check's own name"
    assert "gemini" not in world.admin.routes().engines


@pytest.mark.parametrize(
    ("key", "model", "outcome"),
    [
        ("sk-wrong-key-for-tests", "gemini-2.5-flash", "key_refused"),
        (GOOD, "gemini-not-a-model", "model_not_offered"),
    ],
)
def test_a_refused_key_or_model_leaves_nothing_in_the_gateway(
    client: TestClient, world: Any, key: str, model: str, outcome: str
) -> None:
    answer = _check(client, key=key, roles={"extraction": model}).json()
    assert answer["ok"] is False and answer["check"] is None
    assert answer["models"][0]["outcome"] == outcome
    assert answer["words"] and key not in answer["words"]
    assert _credentials(world) == [], "the refused key is not kept"
    assert world.gateway.entry_for(f"gemini/{model}") is None


def test_add_is_refused_without_a_passed_check(client: TestClient, world: Any) -> None:
    refused = client.post(f"{CHECKS}/not-a-check/add")
    assert refused.status_code == 404
    assert "Check the key" in refused.json()["detail"]["detail"]
    assert client.get("/v1/admin/models").json()["engines"] == []
    bad = _check(client, key="sk-wrong-key-for-tests").json()
    assert bad["check"] is None, "a refused check gives nothing to add"


def test_a_check_not_added_in_15_minutes_is_removed(
    client: TestClient, world: Any, clock: _Clock
) -> None:
    check = _check(client).json()["check"]
    clock.at += timedelta(minutes=15, seconds=1)
    late = client.post(f"{CHECKS}/{check}/add")
    assert late.status_code == 410 and "15 minutes" in late.json()["detail"]["detail"]
    assert _credentials(world) == []
    assert "engine_check_expired" in [e.action for e in world.audit.entries]


def test_a_corrected_key_checked_again_at_once_is_not_held_back_by_the_refused_one(
    client: TestClient, world: Any
) -> None:
    """The gateway cools a refused entry down for about a minute, and its name with it, even once
    deleted (measured on 8 November; the stand-in does the same). Each check's entries are named
    for that check alone, so a key corrected and checked again at once is asked, and the engine
    added after it answers at once under its own name."""
    assert _check(client, key="sk-wrong-key-for-tests").json()["ok"] is False
    again = _check(client).json()
    assert again["ok"] is True, again["models"]
    assert client.post(f"{CHECKS}/{again['check']}/add").status_code == 200
    assert client.post("/v1/admin/models/engines/gemini/test").json()["outcome"] == "ok"


def test_cancel_removes_the_credential(client: TestClient, world: Any) -> None:
    check = _check(client).json()["check"]
    assert _credentials(world) == ["osprey-gemini"]
    assert client.delete(f"{CHECKS}/{check}").status_code == 200
    assert _credentials(world) == []
    assert "engine_check_cancelled" in [e.action for e in world.audit.entries]


def test_a_check_for_an_engine_already_added_is_refused(client: TestClient, world: Any) -> None:
    client.post(f"{CHECKS}/{_check(client).json()['check']}/add")
    again = _check(client)
    assert again.status_code == 422 and "already" in again.json()["detail"]["detail"]


def test_the_key_appears_nowhere_it_must_not(
    client: TestClient,
    world: Any,
    clock: _Clock,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The owner's key test (ruling 7, pattern 3), across every step of the check: a planted key is
    in no response, header, log record, audit entry, the models file or a gateway row in plaintext,
    and in no URL the Glass is sent to; and it did reach the gateway, so the test cannot pass by
    sending nothing."""
    caplog.set_level(logging.DEBUG)
    # The provider takes this key, so the check passes with it.
    world.gateway.providers["gemini"] = StandInProvider(PLANTED, frozenset({"gemini-2.5-flash"}))
    seen: list[str] = []

    def send(method: str, path: str, **kw: Any) -> httpx.Response:
        response = client.request(method, path, **kw)
        seen.append(
            f"{method} {path} {response.status_code} {response.text} {dict(response.headers)}"
        )
        return response

    good = {"provider": ENGINE, "key": PLANTED}
    passed = send("POST", CHECKS, json=good).json()
    assert passed["ok"] is True
    send("DELETE", f"{CHECKS}/{passed['check']}")  # cancelled
    expired = send("POST", CHECKS, json=good).json()["check"]
    clock.at += timedelta(minutes=16)
    send("POST", f"{CHECKS}/{expired}/add")  # expired
    refused = {
        "provider": {**ENGINE, "roles": {"extraction": "gemini-not-a-model"}},
        "key": PLANTED,
    }
    send("POST", CHECKS, json=refused)  # a refusal
    for malformed in ({**good, "extra": 1}, {"provider": ENGINE, "key": PLANTED * 300},
                      {"provider": {**ENGINE, "label": PLANTED}, "key": PLANTED}):  # fmt: skip
        assert send("POST", CHECKS, json=malformed).status_code == 422
    assert send("POST", CHECKS, content=b'{"key": "' + PLANTED.encode() + b'"').status_code == 422
    added = send("POST", CHECKS, json=good).json()["check"]
    send("POST", f"{CHECKS}/{added}/add")  # added
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")

    fragments = (PLANTED, PLANTED[:12], "W3R8", "leak")
    # P4 and P5 (the owner's review): every record formatted whole, the process's own output,
    # and every file under the test's folder, not the models file alone.
    assert _nowhere(world, tmp_path, caplog, capfd, seen, fragments) == {}
    # And it did reach the gateway, so the test cannot pass by sending nothing: the added engine's
    # credential holds it, as the gateway itself reads it.
    assert world.gateway.credential("osprey-gemini") == PLANTED


def test_the_view_offers_this_profile_s_providers_for_the_form(client: TestClient) -> None:
    """The form's provider list comes from the Conduit (Amendment 14 point 1), in the owner's order,
    each with what the form shows: its address or that it asks one, whether it takes a key, its jobs
    alone, its example and its prefix. Off the cloud platform, Bedrock is not among them."""
    providers = client.get("/v1/admin/models").json()["providers"]
    assert [p["id"] for p in providers] == ["gemini", "openai", "anthropic", "azure", "gateway"]
    gemini = providers[0]
    assert gemini["address"] == "https://generativelanguage.googleapis.com"
    assert gemini["address_asked"] is False and gemini["key"] is True
    assert gemini["example"] == "gemini-3.8-flash" and gemini["prefix"] == "gemini"
    anthropic = next(p for p in providers if p["id"] == "anthropic")
    assert anthropic["jobs"] == ["extraction", "vision"], "no transcription offered"
    azure = next(p for p in providers if p["id"] == "azure")
    assert azure["address"] is None and azure["address_asked"] is True and azure["example"] is None
    assert all("hosts" not in p for p in providers), "the form is told what it shows, no more"


def test_on_the_cloud_platform_bedrock_is_offered_with_no_key_and_no_address(
    client: TestClient, world: Any
) -> None:
    world.admin._file.profile = "cloud-platform"
    providers = client.get("/v1/admin/models").json()["providers"]
    bedrock = next(p for p in providers if p["id"] == "bedrock")
    assert bedrock["key"] is False and bedrock["address"] is None
    assert bedrock["address_asked"] is False and "London" in bedrock["note"]


def test_a_passed_check_is_shown_as_being_checked_until_added_cancelled_or_15_minutes(
    client: TestClient, world: Any, clock: _Clock
) -> None:
    """Amendment 14 point 2: a passed check waiting for **Add** is shown in Admin as being checked,
    with when it lapses, so an administrator who left the form can cancel it; never as an engine."""
    check = _check(client).json()["check"]
    held = client.get("/v1/admin/models").json()["checks"]
    assert held == [
        {
            "id": check,
            "engine": "gemini",
            "label": "Google Gemini",
            "by": ADMIN.id,
            "at": "2026-11-15T12:00:00Z",
            "expires_at": "2026-11-15T12:15:00Z",
        }
    ]
    assert client.delete(f"{CHECKS}/{check}").json()["checks"] == []
    _check(client)
    clock.at += timedelta(minutes=15, seconds=1)
    assert client.get("/v1/admin/models").json()["checks"] == [], "a lapsed check is not shown"
    added = client.post(f"{CHECKS}/{_check(client).json()['check']}/add").json()
    assert added["checks"] == [] and added["engines"][0]["provider"]["name"] == "gemini"


def _audited(world: Any, action: str) -> int:
    return [e.action for e in world.audit.entries].count(action)


def test_a_lapsed_check_is_removed_by_the_sweep_with_no_request(
    client: TestClient, world: Any, clock: _Clock
) -> None:
    """Amendment 14 point 3's bound on how long a key is held unadded, told to the owner (point 7):
    the sweep removes a lapsed check's key with no later request to prompt it, audited once."""
    _check(client)
    clock.at += timedelta(minutes=15, seconds=1)
    asyncio.run(world.admin.sweep_checks())
    assert _credentials(world) == []
    assert _audited(world, "engine_check_expired") == 1
    asyncio.run(world.admin.sweep_checks())
    assert _audited(world, "engine_check_expired") == 1, "audited once"
    saved = yaml.safe_load((world.folder / "models.yaml").read_text())
    assert not saved.get("checks"), "the lapsed check is gone from the models file"


def test_the_sweep_runs_by_itself_once_the_conduit_starts(world: Any, clock: _Clock) -> None:
    """Started with the Conduit (`start`) and stopped with it (`close`): nothing has to call it."""

    async def run() -> None:
        world.admin._sweep_seconds = 0.01
        await world.admin.start()
        assert (await world.admin.check(ADMIN.id, _engine(), _key())).ok
        clock.at += timedelta(minutes=16)
        for _ in range(100):
            if not _credentials(world):
                break
            await asyncio.sleep(0.01)
        await world.admin.close()

    asyncio.run(run())
    assert _credentials(world) == []
    assert _audited(world, "engine_check_expired") == 1


def _engine() -> Any:
    from schemas.deployment import ModelProviderConfig

    return ModelProviderConfig.model_validate(ENGINE)


def _key() -> Any:
    from pydantic import SecretStr

    return SecretStr(GOOD)


def test_no_route_adds_an_engine_without_a_passed_check(client: TestClient, world: Any) -> None:
    """The owner's ruling 18: an engine is added only from a passed check, by its id, under 15
    minutes old. The older add route is gone, and no other `POST` under the section adds one."""
    posts = sorted(
        r.path for r in app.routes
        if isinstance(r, APIRoute) and "POST" in r.methods and r.path.startswith("/v1/admin/models")
    )  # fmt: skip
    assert posts == [
        CHECKS,
        f"{CHECKS}/{{check_id}}/add",
        "/v1/admin/models/engines/{name}/test",
    ]
    old = client.post("/v1/admin/models/engines", json={"provider": ENGINE})
    assert old.status_code in (404, 405)
    assert client.get("/v1/admin/models").json()["engines"] == []
    assert world.gateway.stored_ids() == set() and _credentials(world) == []
    assert not hasattr(world.admin, "add_engine"), "no unchecked add left to route to"


def test_a_key_pasted_into_a_model_name_is_refused_before_anything_is_kept(
    client: TestClient, world: Any
) -> None:
    refused = _check(client, roles={"extraction": PLANTED})
    assert refused.status_code == 422, refused.text
    assert PLANTED not in refused.text and "model name looks like a key" in refused.text
    assert _credentials(world) == []
    assert PLANTED not in json.dumps([e.model_dump(mode="json") for e in world.audit.entries])
    assert PLANTED not in "\n".join(world.gateway.raw_rows())


def test_the_key_is_recorded_as_set_by_who_checked_it_and_when(
    client: TestClient, world: Any, clock: _Clock
) -> None:
    """The owner's key rule 3: who set the key, and when, is who typed it at the check."""
    check = _check(client).json()["check"]
    clock.at += timedelta(minutes=5)
    other = ADMIN.model_copy(update={"id": "admin-2"})
    app.dependency_overrides[get_principal] = lambda: other
    added = client.post(f"{CHECKS}/{check}/add").json()
    engine = added["engines"][0]
    assert engine["key_set_by"] == ADMIN.id
    assert engine["key_set_at"].startswith("2026-11-15T12:00:00")
    key_set = next(e for e in world.audit.entries if e.action == "key_set")
    added_row = next(e for e in world.audit.entries if e.action == "engine_added")
    assert key_set.by == ADMIN.id and added_row.by == "admin-2"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": "azure", "api_base": "http://ai.example/openai"}, "provider.api_base"),
        ({"roles": {"extraction": "gemini 3.8 flash"}}, "provider.roles.extraction"),
        # The roles' rule quotes the name it refuses: a key pasted with a space is never echoed.
        ({"roles": {"vision": f"x {PLANTED}"}}, "provider.roles.vision"),
        (
            {"privacy_contract": True, "contract_reference": f"DPA {PLANTED}"},
            "provider.contract_reference",
        ),
    ],
)
def test_a_refused_field_is_named_so_the_form_can_say_it_there(
    client: TestClient, world: Any, change: dict[str, Any], field: str
) -> None:
    """Amendment 14 point 5: a value the engine's own rules refuse is named by its field (the form
    ties the words to it), in the rules' words, never echoing what was sent, the key included."""
    refused = _check(client, key=PLANTED, **change)
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert [f["field"] for f in detail["fields"]] == [field]
    assert detail["fields"][0]["words"] and "Send the engine" not in detail["detail"]
    assert PLANTED not in refused.text and "W3R8" not in refused.text
    assert _credentials(world) == []


# --- the owner's ruling 19: an edit is checked too ----------------------------------------------

ENGINES = "/v1/admin/models/engines"
WRONG = "sk-wrong-key-for-tests"
PROXY = "https://proxy.example.org/v1"


def _added(client: TestClient, key: str | None = GOOD, **engine: Any) -> dict[str, Any]:
    check = _check(client, key=key, **engine).json()
    assert check["ok"], check
    added = client.post(f"{CHECKS}/{check['check']}/add")
    assert added.status_code == 200, added.text
    return dict(added.json())


def _probes(world: Any) -> list[str]:
    """Anything an edit's check left in the gateway: a credential or an entry under its own name."""
    return sorted(
        [c for c in world.gateway._creds if ".check" in c]
        + [i for i in world.gateway.stored_ids() if ".check" in i]
    )


def _file(world: Any) -> str:
    return str((world.folder / "models.yaml").read_text())


def test_an_edited_model_name_is_checked_before_it_is_saved(client: TestClient, world: Any) -> None:
    """Ruling 19: a changed model name runs the check's one call first; a refused one changes
    nothing, the live engine still answering as it did."""
    _added(client)
    before = _file(world)
    nope = {**ENGINE, "roles": {"extraction": "gemini-nope"}}
    refused = client.put(f"{ENGINES}/gemini", json={"provider": nope})
    assert refused.status_code == 422, refused.text
    assert "Nothing was changed" in refused.json()["detail"]["detail"]
    assert _file(world) == before
    assert world.gateway.entry_for("gemini/gemini-2.5-flash") is not None
    assert world.gateway.entry_for("gemini/gemini-nope") is None
    assert world.gateway.credential("osprey-gemini") == GOOD and _probes(world) == []
    asked = len(world.gateway.asked)
    wider = {
        **ENGINE,
        "roles": {"extraction": "gemini-2.5-flash", "vision": "gemini-2.5-pro"},
    }
    assert client.put(f"{ENGINES}/gemini", json={"provider": wider}).status_code == 200
    probed = world.gateway.asked[asked:]
    assert [a.split("/", 1)[1] for a in probed] == ["gemini-2.5-pro"], "only the new model"
    assert probed[0].startswith("gemini.check-"), "under the probe's name, never the live one"
    assert world.gateway.entry_for("gemini/gemini-2.5-pro") is not None and _probes(world) == []


def test_a_label_or_contract_changed_alone_is_saved_with_no_call(
    client: TestClient, world: Any
) -> None:
    _added(client)
    asked = len(world.gateway.asked)
    shown = {
        **ENGINE,
        "label": "Google",
        "privacy_contract": True,
        "contract_reference": "DPA 7",
    }
    assert client.put(f"{ENGINES}/gemini", json={"provider": shown}).status_code == 200
    assert world.gateway.asked[asked:] == []


def test_a_changed_address_takes_its_key_with_it_and_is_checked_there(
    client: TestClient, world: Any
) -> None:
    """Ruling 19 with the owner's earlier ruling (the address decides where the key goes): a moved
    engine needs its key in the same edit, checked at the new address; until it passes, the engine
    keeps its address and its key."""
    _added(client)
    before = _file(world)
    moved = {**ENGINE, "api_base": PROXY}
    keyless = client.put(f"{ENGINES}/gemini", json={"provider": moved})
    assert keyless.status_code == 422 and "key" in keyless.json()["detail"]["detail"]
    wrong = client.put(f"{ENGINES}/gemini", json={"provider": moved, "key": WRONG})
    assert wrong.status_code == 422, wrong.text
    assert _file(world) == before and world.gateway.credential("osprey-gemini") == GOOD
    assert _probes(world) == []
    sent = len(world.gateway.sent)
    assert client.put(f"{ENGINES}/gemini", json={"provider": moved, "key": GOOD}).status_code == 200
    assert (PROXY, GOOD) in world.gateway.sent[sent:], "checked at the new address"
    entry = world.gateway.entry_for("gemini/gemini-2.5-flash")
    assert entry and world.gateway.stored_params(entry)["api_base"] == PROXY
    view = client.get("/v1/admin/models").json()
    assert view["engines"][0]["key_state"] == "set" and _probes(world) == []


def test_a_new_key_is_checked_before_it_replaces_the_one_held(
    client: TestClient, world: Any
) -> None:
    """Ruling 19: a changed key, from the screen or the command line (both `set_key`), is proved
    against each of the engine's models first; a refused one leaves the held key working."""
    _added(client)
    wrong = client.put(f"{ENGINES}/gemini/key", json={"key": WRONG})
    assert wrong.status_code == 422, wrong.text
    assert "keeps" in wrong.json()["detail"]["detail"] and WRONG not in wrong.text
    assert world.gateway.credential("osprey-gemini") == GOOD and _probes(world) == []
    assert client.get("/v1/admin/models").json()["engines"][0]["key_state"] == "set"
    assert world.audit.entries[-1].outcome.startswith("refused")
    from pydantic import SecretStr
    from services.api.model_admin import ModelAdminRefused

    with pytest.raises(ModelAdminRefused):  # the command line's route, `ospreyflow models key`
        asyncio.run(world.admin.set_key("cli:ayan", "gemini", SecretStr(WRONG)))
    assert world.gateway.credential("osprey-gemini") == GOOD
    second = "sk-second-good-key-for-tests"
    world.gateway.providers = {"gemini": StandInProvider(second, frozenset({"gemini-2.5-flash"}))}
    assert client.put(f"{ENGINES}/gemini/key", json={"key": second}).status_code == 200
    assert world.gateway.credential("osprey-gemini") == second and _probes(world) == []


def test_a_key_moved_from_deployment_env_is_moved_unchecked(tmp_path: Path) -> None:
    """Amendment 14's one exception to ruling 19: `ospreyflow` moving the installer's own key out
    of `deployment.env` changes no key, so nothing is asked of the provider at install."""
    from schemas.deployment import ModelProviderConfig
    from services.api.model_keys import move_keys

    from tests.services.api.test_model_admin_routes import World as RoutesWorld


    w = RoutesWorld(tmp_path, providers=[ModelProviderConfig.model_validate(ENGINE)])
    moved, _ = asyncio.run(move_keys(w.admin, [f"GEMINI={WRONG}"], "cli:ayan"))
    assert moved == ["gemini"] and w.gateway.credential("osprey-gemini") == WRONG
    assert w.gateway.asked == []


def test_the_key_appears_nowhere_through_an_edit_or_a_new_key(
    client: TestClient,
    world: Any,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The owner's key test extended to ruling 19: a planted key sent with a moved address, as a new
    key, refused, and in malformed edits, is in no response, header, log record, audit entry, the
    models file or a gateway row in plaintext; and it did reach the gateway."""
    caplog.set_level(logging.DEBUG)
    _added(client)
    seen: list[str] = []

    def send(method: str, path: str, **kw: Any) -> httpx.Response:
        response = client.request(method, path, **kw)
        seen.append(
            f"{method} {path} {response.status_code} {response.text} {dict(response.headers)}"
        )
        return response

    moved = {**ENGINE, "api_base": PROXY}
    # Refused: the provider does not take it yet.
    assert (
        send("PUT", f"{ENGINES}/gemini", json={"provider": moved, "key": PLANTED}).status_code
        == 422
    )
    assert send("PUT", f"{ENGINES}/gemini/key", json={"key": PLANTED}).status_code == 422
    world.gateway.providers = {"gemini": StandInProvider(PLANTED, frozenset({"gemini-2.5-flash"}))}
    for malformed in ({"provider": moved, "key": PLANTED, "extra": 1},
                      {"provider": moved, "key": PLANTED * 300},
                      {"provider": {**moved, "label": PLANTED}, "key": PLANTED}):  # fmt: skip
        assert send("PUT", f"{ENGINES}/gemini", json=malformed).status_code == 422
    assert (
        send("PUT", f"{ENGINES}/gemini", json={"provider": moved, "key": PLANTED}).status_code
        == 200
    )
    assert send("PUT", f"{ENGINES}/gemini/key", json={"key": PLANTED}).status_code == 200
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")

    fragments = (PLANTED, PLANTED[:12], "W3R8", "leak")
    # P4 and P5 (the owner's review): every record formatted whole, the process's own output,
    # and every file under the test's folder, not the models file alone.
    assert _nowhere(world, tmp_path, caplog, capfd, seen, fragments) == {}
    assert world.gateway.credential("osprey-gemini") == PLANTED and _probes(world) == []
