"""Key entry on the guided install page (`06_DECISIONS.md` ADR-137 decision 3, the owner's ruling
"Build key entry"): a write-only field per enabled provider, sent only to the install page's own
server on the admin's machine.

**Where a key goes.** The page holds it in its own memory only, and gives it to the install it runs
as `OSPREY_MODEL_KEY_<NAME>` in that process's environment — exactly how a key typed in the
installer's terminal reaches `harness.apply`, which writes it to `deployment.env` alone. Nothing on
disk holds it before then: not the draft `osprey.yaml`, not the saved answers, not a pending file.

What a mistake would do, and the case that catches it (rule 12):
- the endpoint answering a request that is not from this computer —
  `test_its_key_endpoint_refuses_a_request_that_is_not_from_loopback`;
- the key in a log line or sent back —
  `test_a_key_it_receives_appears_in_no_log_line_and_no_response`;
- the key written to a file the page keeps — `test_a_key_it_receives_is_written_to_no_file`;
- the key never reaching the install —
  `test_the_install_it_runs_is_given_the_key_as_the_terminal_would`;
- the page not saying whether a key is set — `test_the_page_shows_key_set_afterwards`;
- a key set for a provider the draft does not enable, or an empty or spaced one —
  `test_a_key_for_a_provider_not_enabled_is_refused`, `test_an_empty_or_spaced_key_is_refused`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from .test_install_page import TOKEN, Rig, _events

GEMINI_KEY = "AIza-gemini-NEVER-PRINTED-0123456789"
DRAFT = {
    "profile": "local-lite",
    "models": {
        "local_only": False,
        "sendable_handling_codes": ["P"],
        "providers": [
            {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini-2.5-flash"}},
            {"name": "openai", "roles": {"vision": "gpt-4o-mini"}},
        ],
        "defaults": {"extraction": "gemini"},
    },
}


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    for name in ("OSPREY_MODEL_KEY_GEMINI", "OSPREY_MODEL_KEY_OPENAI"):
        monkeypatch.delenv(name, raising=False)
    found = Rig(tmp_path)
    found.draft.write_text(yaml.safe_dump(DRAFT), encoding="utf-8")
    return found


def _send(client: TestClient, name: str = "gemini", key: str = GEMINI_KEY):  # noqa: ANN202
    return client.put(f"/api/install/keys/{name}", json={"key": key})


@pytest.mark.parametrize("client_host", ["203.0.113.5", "10.0.0.7"])
def test_its_key_endpoint_refuses_a_request_that_is_not_from_loopback(
    rig: Rig, client_host: str
) -> None:
    """With the right token, even: the token proves the link, not where the request comes from."""
    remote = TestClient(rig.app(), client=(client_host, 51000), follow_redirects=False)
    reply = remote.put(
        "/api/install/keys/gemini", json={"key": GEMINI_KEY}, headers={"X-Install-Token": TOKEN}
    )
    assert reply.status_code == 403
    assert GEMINI_KEY not in reply.text
    listed = remote.get("/api/install/keys", headers={"X-Install-Token": TOKEN})
    assert listed.status_code == 403
    # Nothing was taken: from this computer, the page still says no key.
    local = TestClient(remote.app, client=("127.0.0.1", 51000))
    keys = local.get("/api/install/keys", headers={"X-Install-Token": TOKEN}).json()
    assert {p["name"]: p["set"] for p in keys["providers"]} == {"gemini": False, "openai": False}


def test_a_key_it_receives_appears_in_no_log_line_and_no_response(
    rig: Rig, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    client = rig.signed()
    replies = [_send(client), client.get("/api/install/keys"), client.get("/api/install/state"),
               client.get("/api/config")]  # fmt: skip
    for reply in replies:
        assert reply.status_code == 200, reply.text
        assert GEMINI_KEY not in reply.text
        assert GEMINI_KEY not in str(reply.headers)
    assert GEMINI_KEY not in caplog.text
    assert all(GEMINI_KEY not in record.getMessage() for record in caplog.records)
    out = capsys.readouterr()
    assert GEMINI_KEY not in out.out + out.err


def test_a_key_it_receives_is_written_to_no_file(rig: Rig, tmp_path: Path) -> None:
    client = rig.signed()
    client.put("/api/install/answers", json={"mode": "lite"})
    assert _send(client).status_code == 200
    holding = [
        p for p in tmp_path.rglob("*") if p.is_file() and GEMINI_KEY.encode() in p.read_bytes()
    ]
    assert holding == []


def test_the_page_shows_key_set_afterwards(rig: Rig) -> None:
    client = rig.signed()
    before = client.get("/api/install/keys").json()["providers"]
    assert before == [
        {"name": "gemini", "label": "Gemini", "variable": "OSPREY_MODEL_KEY_GEMINI", "set": False},
        {"name": "openai", "label": "OpenAI", "variable": "OSPREY_MODEL_KEY_OPENAI", "set": False},
    ]
    reply = _send(client)
    assert reply.json() == {"name": "gemini", "set": True}
    after = {p["name"]: p["set"] for p in client.get("/api/install/keys").json()["providers"]}
    assert after == {"gemini": True, "openai": False}


def test_a_key_already_in_the_installers_terminal_shows_as_set(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OSPREY_MODEL_KEY_OPENAI", "sk-from-the-terminal")
    providers = rig.signed().get("/api/install/keys").json()["providers"]
    assert {p["name"]: p["set"] for p in providers} == {"gemini": False, "openai": True}


def test_the_install_it_runs_is_given_the_key_as_the_terminal_would(rig: Rig) -> None:
    rig.script = (
        "import os; print('key given:', os.environ.get('OSPREY_MODEL_KEY_GEMINI') == "
        f"{GEMINI_KEY!r}); print('other:', 'OSPREY_MODEL_KEY_OPENAI' in os.environ)"
    )
    client = rig.signed()
    client.put("/api/install/answers", json={"mode": "lite"})
    assert _send(client).status_code == 200
    events = _events(client)
    lines = [d["line"] for n, d in events if n == "message"]
    assert lines == ["key given: True", "other: False"]
    assert all(GEMINI_KEY not in str(d) for _, d in events)


def test_a_key_for_a_provider_not_enabled_is_refused(rig: Rig) -> None:
    client = rig.signed()
    reply = _send(client, name="anthropic")
    assert reply.status_code == 422
    assert "anthropic" in reply.json()["error"] and GEMINI_KEY not in reply.text


@pytest.mark.parametrize("key", ["", "   ", "two words", "line\nbreak"])
def test_an_empty_or_spaced_key_is_refused(rig: Rig, key: str) -> None:
    client = rig.signed()
    reply = _send(client, key=key)
    assert reply.status_code == 422
    assert {p["name"]: p["set"] for p in client.get("/api/install/keys").json()["providers"]} == {
        "gemini": False, "openai": False}  # fmt: skip


def test_the_single_provider_is_given_its_own_variable(rig: Rig) -> None:
    rig.draft.write_text(
        yaml.safe_dump({"models": {"local_only": False, "provider": {
            "name": "openai", "roles": {"extraction": "gpt-4o-mini"}}}}),
        encoding="utf-8",
    )  # fmt: skip
    rig.script = "import os; print(os.environ.get('OSPREY_MODEL_PROVIDER_KEY') == 'sk-one')"
    client = rig.signed()
    assert client.get("/api/install/keys").json()["providers"][0]["variable"] == (
        "OSPREY_MODEL_PROVIDER_KEY"
    )
    client.put("/api/install/answers", json={"mode": "lite"})
    assert _send(client, name="openai", key="sk-one").status_code == 200
    assert [d["line"] for n, d in _events(client) if n == "message"] == ["True"]
