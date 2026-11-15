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

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
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
    client: TestClient, world: Any, clock: _Clock, caplog: pytest.LogCaptureFixture
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
    where = {
        "responses, headers and URLs": "\n".join(seen),
        "logs": "\n".join(r.getMessage() + repr(r.args) for r in caplog.records),
        "audit": json.dumps([e.model_dump(mode="json") for e in world.audit.entries]),
        "models file": (world.folder / "models.yaml").read_text(),
        "gateway rows": "\n".join(world.gateway.raw_rows()),
    }
    leaked = {w: f for w, text in where.items() for f in fragments if f in text}
    assert leaked == {}
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
