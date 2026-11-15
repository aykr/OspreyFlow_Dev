# ruff: noqa: F811 - the check tests' fixtures, imported, are the parameters of these cases
"""The owner's independent review of *Admin › Models*' key handling (15 November 2026,
`process/lanes/admin-forms/KEY_REVIEW_2026-11-15.md`; the owner's rulings 21 to 28; ADR-135
Amendment 14 point 10), through the real app and the stand-in gateway, with synthetic keys only.

What a mistake would do, and the case that catches it (rule 12):
- a refused model name echoed or audited (ruling 22, Fix A(1) and (3)):
  `test_a_refused_model_name_is_said_by_its_job_never_echoed_nor_audited`;
- a name that does not look like a model name taken (ruling 23, Fix A(2)):
  `test_a_model_name_is_taken_only_if_it_looks_like_one`, and no real one refused:
  `test_every_catalogue_name_and_real_model_name_looks_like_one`;
- a key in a shape the key rule misses, typed as a model name (P1):
  `test_a_key_in_a_model_name_box_appears_nowhere`;
- the same shapes as the real key (P2): `test_an_odd_shaped_key_appears_nowhere`;
- a key-shaped field name echoed in a refusal (Fix B):
  `test_a_key_shaped_field_name_is_never_echoed`;
- a validator's words quoting a key in another form (Fix C):
  `test_a_refused_field_is_said_in_fixed_words_never_the_validator_s`;
- a key in an error report, or a credential left by an error (Fix D, P3):
  `test_an_unexpected_transport_error_reports_no_key_and_leaves_no_credential`;
- a key as a non-string, or in the address (P9): `test_a_key_not_sent_as_text_is_refused_unechoed`,
  `test_a_key_in_the_address_is_refused`;
- a credential left by a Conduit stopped mid-check (ruling 25):
  `test_a_check_stopped_after_its_key_reached_the_gateway_is_swept_with_its_key`.
P4 (every log record formatted whole, and the process's own output) and P5 (every file in the test's
folder) are in `_nowhere`, used by each case above that sends a key.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from adapters.model_litellm.stand_in import StandInProvider
from fastapi.testclient import TestClient
from services.api import model_catalogue
from services.api.app import app

from tests.services.api.test_model_admin_routes import GOOD
from tests.services.api.test_model_engine_checks import (  # noqa: F401 - fixtures
    CHECKS,
    ENGINE,
    ENGINES,
    PROXY,
    _added,
    _check,
    _nowhere,
    client,
    clock,
    world,
)

#: Synthetic keys in the shapes the key rule (`model_looks_like_a_key`) did not catch: a UUID, a
#: 16-character mixed key, an all lower-case hyphenated token (the owner's review, Fix A).
ODD = {
    "uuid": "3f2a9c1e-7b4d-4e8a-9c0f-5d6e7a8b9c0d",
    "short": "Zx81Kq4Lm2Np7Rs0",
    "lower-hyphen": "plnt-wq7r-x2kd-m9vt",
}
#: A key quoted by a validator's `repr` comes back escaped, which an exact-match redaction misses.
QUOTED = "sk-PLANTED'q\\W3R8-quoted-key"


def _sender(client: TestClient, seen: list[str]) -> Any:
    def send(method: str, path: str, **kw: Any) -> httpx.Response:
        response = client.request(method, path, **kw)
        seen.append(
            f"{method} {path} {response.status_code} {response.text} {dict(response.headers)}"
        )
        return response

    return send


# --- Fix A: a model name ---------------------------------------------------------------------


def test_a_refused_model_name_is_said_by_its_job_never_echoed_nor_audited(
    client: TestClient, world: Any
) -> None:
    """The owner's ruling 22: the check's answer, the screen and the audit say the job and its
    outcome, never the typed name."""
    typed = "gemini-not-offered-x7"
    answer = _check(client, roles={"extraction": typed, "vision": "gemini-2.5-flash"}).json()
    assert answer["ok"] is False
    assert typed not in json.dumps(answer)
    refused = next(m for m in answer["models"] if not m["ok"])
    assert refused["roles"] == ["extraction"] and "model" not in refused
    assert refused["words"].startswith("Extraction and Ask:"), refused["words"]
    checked = next(e for e in world.audit.entries if e.action == "engine_checked")
    assert typed not in json.dumps(checked.model_dump(mode="json"))
    assert "extraction: model_not_offered" in checked.outcome
    _added(client)
    edited = client.put(
        f"{ENGINES}/gemini", json={"provider": {**ENGINE, "roles": {"extraction": typed}}}
    )
    assert edited.status_code == 422 and typed not in edited.text
    assert "Extraction and Ask:" in edited.json()["detail"]["detail"]
    assert typed not in json.dumps([e.model_dump(mode="json") for e in world.audit.entries])


#: Every real model name the form may meet: the catalogue's examples, the names in this build's
#: tests and fixtures, and the shapes a deployment or a client's gateway names a model by.
REAL_NAMES = [
    "gemini-3.8-flash", "gemini-2.5-flash", "gpt-6.1-sol", "gpt-4o-mini", "gpt-4o-mini-2024-07-18",
    "claude-sonnet-5-5", "amazon.nova-pro-v1:0", "anthropic.claude-3-haiku-20240307-v1:0",
    "my-deployment-2024-08-06", "acme-chat", "acme_chat", "qwen2.5:7b-instruct",
    "Systran/faster-whisper-tiny.en", "models/gemini-pro", "publishers/google/models/gemini@001",
    "moondream:1.8b-v2-q4_K_M", "all-minilm:22m-l6-v2-fp16", "g-flash",
]  # fmt: skip


def test_every_catalogue_name_and_real_model_name_looks_like_one() -> None:
    """Ruling 23, generously: no real model name is refused, the catalogue's own examples first."""
    from services.api.model_admin import model_name_refusal

    examples = [p.example for p in model_catalogue.CATALOGUE if p.example]
    assert examples, "the catalogue's examples are read"
    refused = {n: model_name_refusal("extraction", n) for n in [*examples, *REAL_NAMES]}
    assert {n: w for n, w in refused.items() if w} == {}


@pytest.mark.parametrize(
    "name",
    ["gemini?x", "a" * 129, "model<script>", "naïve-model", "gemini,flash", "x#y", ODD["uuid"]],
    ids=["question", "too-long", "angle", "accent", "comma", "hash", "uuid"],
)
def test_a_model_name_is_taken_only_if_it_looks_like_one(
    client: TestClient, world: Any, name: str
) -> None:
    """Ruling 23: letters, digits and . _ - : / @, up to 128; a UUID is a key's shape, not a
    model's. Refused at the job's field in fixed words, nothing handed to the gateway, never
    echoed."""
    refused = _check(client, roles={"extraction": name})
    assert refused.status_code == 422, refused.text
    assert name not in refused.text
    assert world.gateway._creds == {}  # noqa: SLF001 - nothing was handed over
    _added(client)
    edited = client.put(
        f"{ENGINES}/gemini", json={"provider": {**ENGINE, "roles": {"extraction": name}}}
    )
    assert edited.status_code == 422 and name not in edited.text


@pytest.mark.parametrize("shape", sorted(ODD))
def test_a_key_in_a_model_name_box_appears_nowhere(
    client: TestClient,
    world: Any,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
    shape: str,
) -> None:
    """P1: a synthetic key in each shape the key rule missed, typed as a model name, on **Check**
    and on **Edit**: in no answer, audit, log, output or file."""
    caplog.set_level(logging.DEBUG)
    key = ODD[shape]
    seen: list[str] = []
    send = _sender(client, seen)
    send("POST", CHECKS, json={"provider": {**ENGINE, "roles": {"extraction": key}}, "key": GOOD})
    _added(client)
    send("PUT", f"{ENGINES}/gemini", json={"provider": {**ENGINE, "roles": {"extraction": key}}})
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")
    assert _nowhere(world, tmp_path, caplog, capfd, seen, (key,)) == {}


@pytest.mark.parametrize("shape", sorted(ODD))
def test_an_odd_shaped_key_appears_nowhere(
    client: TestClient,
    world: Any,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
    clock: Any,
    shape: str,
) -> None:
    """P2: the owner's key test with the real key in each odd shape (the planted one starts `sk-`):
    checked, cancelled, refused, added, edited with a moved address, replaced, and refused as a new
    key;
    and it did reach the gateway."""
    caplog.set_level(logging.DEBUG)
    key = ODD[shape]
    world.gateway.providers = {"gemini": StandInProvider(key, frozenset({"gemini-2.5-flash"}))}
    seen: list[str] = []
    send = _sender(client, seen)
    good = {"provider": ENGINE, "key": key}
    send("DELETE", f"{CHECKS}/{send('POST', CHECKS, json=good).json()['check']}")
    send(
        "POST",
        CHECKS,
        json={"provider": {**ENGINE, "roles": {"extraction": "gemini-nope"}}, "key": key},
    )
    for malformed in ({**good, "extra": 1}, {"provider": ENGINE, "key": key * 300}):
        assert send("POST", CHECKS, json=malformed).status_code == 422
    send("POST", f"{CHECKS}/{send('POST', CHECKS, json=good).json()['check']}/add")
    moved = {**ENGINE, "api_base": PROXY}
    assert send("PUT", f"{ENGINES}/gemini", json={"provider": moved, "key": key}).status_code == 200
    assert send("PUT", f"{ENGINES}/gemini/key", json={"key": key}).status_code == 200
    world.gateway.providers = {"gemini": StandInProvider(GOOD, frozenset({"gemini-2.5-flash"}))}
    assert send("PUT", f"{ENGINES}/gemini/key", json={"key": key}).status_code == 422
    send("GET", "/v1/admin/models")
    send("GET", "/v1/admin/models/history")
    assert _nowhere(world, tmp_path, caplog, capfd, seen, (key, key[:12])) == {}
    assert world.gateway.credential("osprey-gemini") == key


# --- Fix B and C: the refusals' own words ---------------------------------------------------------

PLANTED = "sk-PLANTED-review-key-W3R8-do-not-leak"


@pytest.mark.parametrize(
    "body",
    [
        {"provider": {**ENGINE, PLANTED: 1}},
        {"provider": ENGINE, PLANTED: "x"},
        {"provider": {**ENGINE, "roles": {PLANTED: "gemini-2.5-flash"}}},
    ],
    ids=["extra-in-provider", "extra-at-top", "key-under-roles"],
)
def test_a_key_shaped_field_name_is_never_echoed(
    client: TestClient, world: Any, body: dict[str, Any]
) -> None:
    """Fix B: a refusal names fields from a fixed list, never a field name that was sent."""
    _added(client)
    for method, path in (("PUT", f"{ENGINES}/gemini"), ("POST", CHECKS)):
        answer = client.request(
            method, path, json={**body, "key": GOOD} if method == "POST" else body
        )
        assert answer.status_code == 422, answer.text
        assert PLANTED not in answer.text and "W3R8" not in answer.text
    assert PLANTED not in json.dumps([e.model_dump(mode="json") for e in world.audit.entries])


@pytest.mark.parametrize(
    "change",
    [
        {"roles": {"extraction": f"x {QUOTED}"}},
        {"api_base": f"http://{QUOTED}.example"},
        {"privacy_contract": True, "contract_reference": f"DPA {QUOTED}"},
        {"name": QUOTED},
    ],
    ids=["roles", "address", "reference", "name"],
)
def test_a_refused_field_is_said_in_fixed_words_never_the_validator_s(
    client: TestClient, world: Any, change: dict[str, Any]
) -> None:
    """Fix C: a validator may quote what it refused in another form (`repr` escapes a quote and a
    backslash), which an exact-match redaction misses; each field's refusal is fixed words."""
    from services.api.model_admin import FIELD_WORDS

    _added(client)
    for method, path in (("POST", CHECKS), ("PUT", f"{ENGINES}/gemini")):
        body: dict[str, Any] = {"provider": {**ENGINE, **change}}
        if method == "POST":
            body["key"] = GOOD
        answer = client.request(method, path, json=body)
        assert answer.status_code == 422, answer.text
        assert "W3R8" not in answer.text and "PLANTED" not in answer.text
        fields = answer.json()["detail"].get("fields") or []
        assert fields and all(f["words"] in FIELD_WORDS.values() or f["words"].endswith(
            FIELD_WORDS["provider.roles"]) for f in fields), fields  # fmt: skip


# --- Fix D: an unexpected error -------------------------------------------------------------------


@pytest.mark.parametrize("where", ["/credentials", "/chat/completions"])
def test_an_unexpected_transport_error_reports_no_key_and_leaves_no_credential(
    world: Any,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
    where: str,
) -> None:
    """P3: the gateway's transport raises an error that is not httpx's, while the key is handed over
    and again during the proving call: no answer, log record (its traceback formatted whole), output
    or file holds the key, and no credential is left, on **Check** and on a new key."""
    caplog.set_level(logging.DEBUG)
    transport = world.admin._gateway.http._transport  # noqa: SLF001
    handler = transport.handler

    def failing(request: httpx.Request) -> httpx.Response:
        if request.url.path == where and request.method == "POST":
            raise RuntimeError("the transport failed")
        return handler(request)

    seen: list[str] = []
    client = TestClient(app, raise_server_exceptions=False)
    send = _sender(client, seen)
    transport.handler = failing
    assert send("POST", CHECKS, json={"provider": ENGINE, "key": PLANTED}).status_code >= 500
    assert world.gateway._creds == {}  # noqa: SLF001
    transport.handler = handler
    _added(client)
    transport.handler = failing
    assert send("PUT", f"{ENGINES}/gemini/key", json={"key": PLANTED}).status_code >= 500
    transport.handler = handler
    assert sorted(world.gateway._creds) == ["osprey-gemini"]  # noqa: SLF001 - the probe's is gone
    assert world.gateway.credential("osprey-gemini") == GOOD
    assert _nowhere(world, tmp_path, caplog, capfd, seen, (PLANTED, "W3R8")) == {}


# --- P9: a key not sent as text, or in the address ----------------------------------------------


@pytest.mark.parametrize(
    "key", [12345678901234567890, [PLANTED], {"k": PLANTED}], ids=["number", "list", "object"]
)
def test_a_key_not_sent_as_text_is_refused_unechoed(
    client: TestClient, world: Any, key: Any
) -> None:
    _added(client)
    moved = {**ENGINE, "api_base": PROXY}
    for method, path, body in (
        ("PUT", f"{ENGINES}/gemini/key", {"key": key}),
        ("POST", CHECKS, {"provider": {**ENGINE, "name": "openai"}, "key": key}),
        ("PUT", f"{ENGINES}/gemini", {"provider": moved, "key": key}),
    ):
        answer = client.request(method, path, json=body)
        assert answer.status_code == 422, (path, answer.text)
        assert PLANTED not in answer.text and "1234567890123" not in answer.text
    assert world.gateway.credential("osprey-gemini") == GOOD


def test_a_key_in_the_address_is_refused(client: TestClient, world: Any) -> None:
    """P9: a key is taken from the body alone; one in the query string is refused in fixed words,
    whatever the body holds, and nothing is changed."""
    _added(client)
    for method, path, body in (
        ("PUT", f"{ENGINES}/gemini/key", {"key": GOOD}),
        ("POST", CHECKS, {"provider": {**ENGINE, "name": "openai"}, "key": GOOD}),
        ("PUT", f"{ENGINES}/gemini", {"provider": {**ENGINE, "label": "Changed"}}),
    ):
        answer = client.request(method, f"{path}?key={PLANTED}", json=body)
        assert answer.status_code == 422, (path, answer.text)
        assert PLANTED not in answer.text and "never in the address" in answer.text
    assert (
        client.get("/v1/admin/models").json()["engines"][0]["provider"]["label"] == "Google Gemini"
    )


# --- ruling 25: a Conduit stopped mid-check -----------------------------------------------------


def test_a_check_stopped_after_its_key_reached_the_gateway_is_swept_with_its_key(
    client: TestClient, world: Any, clock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's ruling 25: the check's record is written before the key goes to the gateway, so a
    Conduit stopped between the two (no handler of its own running) leaves a record the sweep
    removes, credential and all, with no credential ever read back."""
    gateway = world.admin._gateway  # noqa: SLF001

    async def stopped(*_a: Any, **_k: Any) -> Any:
        raise SystemExit  # the process ends here: nothing after it runs

    async def no_cleanup(_name: str) -> None:
        return None

    saves: list[object] = []
    save = world.admin._save  # noqa: SLF001

    def first_save_only(settings: Any) -> None:
        # A stopped process writes nothing after it stops: only the record made before the key.
        if not saves:
            save(settings)
        saves.append(settings)

    monkeypatch.setattr(world.admin, "_prove", stopped)
    monkeypatch.setattr(world.admin, "_save", first_save_only)
    monkeypatch.setattr(gateway, "delete_credential", no_cleanup)
    with pytest.raises(SystemExit):
        asyncio.run(world.admin.check("admin-1", _engine(), _key()))
    assert world.gateway.credential("osprey-gemini") == GOOD, (
        "the orphan, as a killed check leaves it"
    )
    monkeypatch.undo()
    again = world.make_admin()
    again._now = clock  # noqa: SLF001
    assert again.view().checks == [], "a check not yet passed is never offered for Add"
    clock.at += timedelta(minutes=16)
    asyncio.run(again.sweep_checks())
    assert world.gateway._creds == {}  # noqa: SLF001
    assert world.gateway.credential_reads == 0


def test_a_passed_check_whose_record_cannot_be_saved_takes_its_key_with_it(
    client: TestClient, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Since ruling 25 the check's record is written before the key, so a full disk refuses there,
    before anything is handed over; this is the other place: the key in the gateway, every model
    answered, and the record that says so cannot be written. The key goes with the refusal."""
    save = world.admin._save  # noqa: SLF001
    saves: list[object] = []

    def full_after_the_first(settings: Any) -> None:
        saves.append(settings)
        if len(saves) > 1:
            raise OSError(28, "No space left on device")
        save(settings)

    monkeypatch.setattr(world.admin, "_save", full_after_the_first)
    answer = _check(client)
    assert answer.status_code == 500 and "not saved" in answer.json()["detail"]["detail"]
    assert world.gateway._creds == {}  # noqa: SLF001


def _engine() -> Any:
    from schemas.deployment import ModelProviderConfig

    return ModelProviderConfig.model_validate(ENGINE)


def _key() -> Any:
    from pydantic import SecretStr

    return SecretStr(GOOD)
