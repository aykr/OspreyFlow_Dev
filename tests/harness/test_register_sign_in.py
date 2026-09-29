"""Registering the launcher's sign-in on a Keycloak that is already running.

`06_DECISIONS.md` ADR-051. A realm import runs only when Keycloak first starts against an empty
database, so a deployment that was applied before the launcher had a sign-in has a realm with no
`osprey-launcher` client and no `osprey-demo-admin` subject, and re-rendering `realm.json` changes
nothing there. `harness/register_sign_in.py` adds them through the admin API, and the same module's
password helpers serve `apply` for a fresh deployment.

The fake below is a Keycloak that can say no (standing rule 15: a fixture that only ever says yes
proves nothing about the refusal paths). It refuses a wrong admin password, refuses duplicates, can
be told to refuse a password reset, and can be unreachable. Each test names what it would catch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.keycloak_admin import RealmConfigurationFailed
from harness.realm import (
    ADMIN_ROLE,
    DEMO_ADMIN_SUBJECT,
    DEMO_ANALYST_SUBJECT,
    HARNESS_CLIENT_ID,
    LAUNCHER_CLIENT_ID,
    render_realm,
)

from harness import keycloak_admin, register_sign_in
from schemas.deployment import OspreyConfig

ISSUER = "http://kc.test"
ADMIN_PASSWORD = "the-keycloak-admin-password"
SECRET_SHAPED = "s3cret-value-that-must-never-be-printed"


def _config() -> OspreyConfig:
    return OspreyConfig.model_validate(
        yaml.safe_load("network:\n  public_origin: http://localhost:9999\n")
    )


class FakeKeycloak:
    """Just enough of the admin API, with its refusals."""

    def __init__(self) -> None:
        self.clients: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}
        self.passwords: dict[str, str] = {}
        self.refuse_reset = False
        self.unreachable = False
        self.calls: list[tuple[str, str]] = []

    def call(
        self,
        url: str,
        *,
        token: str | None = None,
        data: Any = None,
        form: bool = False,
        method: str | None = None,
    ) -> tuple[int, Any]:
        if self.unreachable:
            raise RealmConfigurationFailed(f"{url} unreachable: connection refused")
        verb = method or ("POST" if data is not None else "GET")
        path = url.removeprefix(ISSUER)
        self.calls.append((verb, path))
        if path == "/realms/master/protocol/openid-connect/token":
            if data["password"] != ADMIN_PASSWORD:
                return 401, {"error": "invalid_grant"}
            return 200, {"access_token": "admin-token"}
        if token != "admin-token":
            return 401, {"error": "no token"}
        route = path.removeprefix("/admin/realms/osprey")
        if route.startswith("/clients?clientId="):
            wanted = route.split("=", 1)[1]
            return 200, [c for c in self.clients.values() if c["clientId"] == wanted]
        if route == "/clients" and verb == "POST":
            if data["clientId"] in {c["clientId"] for c in self.clients.values()}:
                return 409, {"errorMessage": "Client already exists"}
            identifier = f"cid-{len(self.clients) + 1}"
            self.clients[identifier] = {**data, "id": identifier}
            return 201, ""
        if route.startswith("/users?username="):
            wanted = route.split("=", 1)[1].split("&")[0]
            return 200, [u for u in self.users.values() if u["username"] == wanted]
        if route == "/users" and verb == "POST":
            if data["username"] in {u["username"] for u in self.users.values()}:
                return 409, {"errorMessage": "User exists with same username"}
            identifier = f"uid-{len(self.users) + 1}"
            self.users[identifier] = {**data, "id": identifier}
            return 201, ""
        if route.endswith("/reset-password") and verb == "PUT":
            if self.refuse_reset:
                return 403, {"error": "forbidden"}
            identifier = route.split("/")[2]
            self.passwords[self.users[identifier]["username"]] = data["value"]
            return 204, ""
        raise AssertionError(f"the fake has no route for {verb} {path}")

    def seed_analyst(self) -> None:
        self.users["uid-a"] = {"id": "uid-a", "username": DEMO_ANALYST_SUBJECT}


@pytest.fixture
def keycloak(monkeypatch: pytest.MonkeyPatch) -> FakeKeycloak:
    fake = FakeKeycloak()
    monkeypatch.setattr(keycloak_admin, "_call", fake.call)
    return fake


def _env(tmp_path: Path, *lines: str) -> Path:
    env = tmp_path / "deployment.env"
    env.write_text(
        "\n".join([f"OSPREY_KEYCLOAK_ADMIN_PASSWORD={ADMIN_PASSWORD}", *lines]) + "\n",
        encoding="utf-8",
    )
    return env


def _register(env: Path) -> list[str]:
    return register_sign_in.register(issuer=ISSUER, realm="osprey", env_path=env, config=_config())


def _env_values(env: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        out[name] = value
    return out


# --- the password helper `apply` uses for a fresh deployment ---


def test_the_demo_admins_password_is_set_on_the_admin_and_not_on_the_analyst(
    keycloak: FakeKeycloak,
) -> None:
    """Catches a helper that resets whichever demo subject it finds first, which would hand the
    analyst the admin's password."""
    keycloak.seed_analyst()
    keycloak.users["uid-b"] = {"id": "uid-b", "username": DEMO_ADMIN_SUBJECT}

    keycloak_admin.set_demo_admin_password(
        issuer=ISSUER,
        realm="osprey",
        admin_user="admin",
        admin_password=ADMIN_PASSWORD,
        password=SECRET_SHAPED,
    )

    assert keycloak.passwords == {DEMO_ADMIN_SUBJECT: SECRET_SHAPED}


def test_a_missing_demo_admin_is_named_rather_than_silently_skipped(
    keycloak: FakeKeycloak,
) -> None:
    keycloak.seed_analyst()
    with pytest.raises(RealmConfigurationFailed, match=DEMO_ADMIN_SUBJECT):
        keycloak_admin.set_demo_admin_password(
            issuer=ISSUER,
            realm="osprey",
            admin_user="admin",
            admin_password=ADMIN_PASSWORD,
            password="x",
        )


def test_a_wrong_keycloak_admin_password_is_reported_as_refused(keycloak: FakeKeycloak) -> None:
    with pytest.raises(RealmConfigurationFailed, match="could not authenticate"):
        keycloak_admin.set_demo_admin_password(
            issuer=ISSUER,
            realm="osprey",
            admin_user="admin",
            admin_password="wrong",
            password="x",
        )


# --- registering on a running Keycloak ---


def test_registering_adds_both_sign_in_clients_and_the_demo_admin_exactly_as_the_realm_renders_them(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Catches a registration that hand-writes its own copy of the client: the running deployment
    would then differ from the one a fresh apply builds, and only on the machine that was there
    before."""
    env = _env(tmp_path)
    _register(env)

    rendered = render_realm(_config(), demo_analyst=True)
    wanted = {
        c["clientId"]: c
        for c in rendered["clients"]
        if c["clientId"] in (LAUNCHER_CLIENT_ID, HARNESS_CLIENT_ID)
    }
    registered = {
        c["clientId"]: {k: v for k, v in c.items() if k != "id"} for c in keycloak.clients.values()
    }
    assert registered == wanted, "both sign-in clients, exactly as a fresh apply renders them"

    (admin,) = [u for u in rendered["users"] if u["username"] == DEMO_ADMIN_SUBJECT]
    (created,) = keycloak.users.values()
    assert {k: v for k, v in created.items() if k != "id"} == admin
    assert created["attributes"]["roles"] == [ADMIN_ROLE]


def test_registering_writes_the_demo_admins_password_to_the_env_file_and_it_works(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    env = _env(tmp_path)
    _register(env)

    written = _env_values(env)["OSPREY_DEMO_ADMIN_PASSWORD"]
    assert written
    assert keycloak.passwords[DEMO_ADMIN_SUBJECT] == written, (
        "the file names a password Keycloak was never given"
    )


def test_registering_twice_changes_nothing_and_keeps_the_same_password(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Catches a second run that duplicates the client (Keycloak answers 409, which must not be
    treated as failure) or rotates the password the operator has already been told."""
    env = _env(tmp_path)
    _register(env)
    first = _env_values(env)["OSPREY_DEMO_ADMIN_PASSWORD"]

    _register(env)

    assert len(keycloak.clients) == 2
    assert len(keycloak.users) == 1
    assert _env_values(env)["OSPREY_DEMO_ADMIN_PASSWORD"] == first
    assert keycloak.passwords[DEMO_ADMIN_SUBJECT] == first


def test_registering_after_keycloak_restarts_empty_restores_the_same_password(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Keycloak's database is deliberately not persisted (`harness/render.py`), so a restart drops
    the user and its password while the env file still names one. Running again must make the file
    true again, not mint a second password."""
    env = _env(tmp_path)
    _register(env)
    first = _env_values(env)["OSPREY_DEMO_ADMIN_PASSWORD"]
    keycloak.clients.clear()
    keycloak.users.clear()
    keycloak.passwords.clear()

    _register(env)

    assert keycloak.passwords[DEMO_ADMIN_SUBJECT] == first


def test_a_refused_password_reset_leaves_the_env_file_without_a_password_that_does_not_work(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    keycloak.refuse_reset = True
    env = _env(tmp_path)

    with pytest.raises(RealmConfigurationFailed, match="password"):
        _register(env)

    assert "OSPREY_DEMO_ADMIN_PASSWORD" not in _env_values(env)


def test_a_refused_admin_password_says_which_file_and_what_to_do_about_it(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Seen on the running deployment, 29 September 2026: `make register-sign-in` stopped with a
    bare `401 invalid_grant`. The cause was that `deployment.env` had been rewritten by a later
    render, so it named an admin password the still-running Keycloak (started from the earlier one)
    did not have. The message must say that, and how to get the two back in step, in the
    product's own words, without printing any password."""
    env = tmp_path / "deployment.env"
    env.write_text("OSPREY_KEYCLOAK_ADMIN_PASSWORD=stale-value-9911\n", encoding="utf-8")

    with pytest.raises(RealmConfigurationFailed) as refused:
        _register(env)

    message = str(refused.value)
    assert "deployment.env" in message
    assert "started from an earlier" in message
    assert "--force-recreate keycloak" in message
    assert "stale-value-9911" not in message
    assert "invalid_grant" not in message, "the protocol detail is not the explanation"


def test_a_wrong_admin_password_in_the_env_file_stops_before_anything_is_created(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    env = tmp_path / "deployment.env"
    env.write_text("OSPREY_KEYCLOAK_ADMIN_PASSWORD=stale\n", encoding="utf-8")

    with pytest.raises(RealmConfigurationFailed, match="refused the administrator password"):
        _register(env)

    assert not keycloak.clients
    assert not keycloak.users


def test_an_unreachable_keycloak_is_reported_as_unreachable_not_as_a_refusal(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """ADR-044: 'cannot reach the identity provider' and 'the identity provider said no' are
    different outcomes and the operator's next step differs."""
    keycloak.unreachable = True
    with pytest.raises(RealmConfigurationFailed, match="unreachable"):
        _register(_env(tmp_path))


def test_a_deployment_that_was_never_applied_is_named_not_guessed_at(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    with pytest.raises(RealmConfigurationFailed, match="deployment.env"):
        register_sign_in.register(
            issuer=ISSUER,
            realm="osprey",
            env_path=tmp_path / "missing" / "deployment.env",
            config=_config(),
        )


def test_the_summary_never_carries_a_password(
    keycloak: FakeKeycloak, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path)

    lines = _register(env)
    register_sign_in.print_summary(lines, env)

    out = capsys.readouterr().out + json.dumps(lines)
    assert _env_values(env)["OSPREY_DEMO_ADMIN_PASSWORD"] not in out
    assert ADMIN_PASSWORD not in out
    assert DEMO_ADMIN_SUBJECT in out
    assert "OSPREY_DEMO_ADMIN_PASSWORD" in out
