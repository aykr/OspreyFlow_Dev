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
from harness import keycloak_admin, register_sign_in
from harness.keycloak_admin import RealmConfigurationFailed
from harness.keycloak_theme import DISPLAY_NAME, THEME_NAME
from harness.realm import (
    ADMIN_ROLE,
    DEMO_ADMIN_SUBJECT,
    DEMO_ANALYST_SUBJECT,
    HARNESS_CLIENT_ID,
    HARNESS_ORIGIN,
    HARNESS_REDIRECT_URI,
    render_realm,
)

from schemas.deployment import OspreyConfig

ISSUER = "http://kc.test"
ADMIN_PASSWORD = "the-keycloak-admin-password"
DEMO_ADMIN_ROLES = [ADMIN_ROLE, "analyst", "data_engineer"]
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
        # A realm imported from `realm.json` starts with custom user attributes switched off, and
        # Keycloak then silently discards them when a user is created (no error, no warning).
        self.unmanaged_attributes = "DISABLED"
        self.realm: dict[str, Any] = {"realm": "osprey", "enabled": True}
        # Themes Keycloak can see. The OspreyFlow one is there only if compose mounted it.
        self.themes = ["keycloak", "keycloak.v2"]
        self.calls: list[tuple[str, str]] = []
        # ADR-112 Amendment 1: the Conduit's client, its service account, and realm-management's
        # roles — so `register` can bring the account's grants up to date on every refresh.
        # Kept apart from `clients`, which the sign-in tests count.
        self.system_clients = [{"clientId": "osprey-conduit", "id": "cid-conduit"},
                               {"clientId": "realm-management", "id": "cid-rm"}]  # fmt: skip
        self.service_account = {"id": "uid-sa", "username": "service-account-osprey-conduit"}
        self.realm_management_roles = ["impersonation", "view-users", "manage-users", "manage-clients",
                                       "query-users", "realm-admin"]  # fmt: skip
        self.granted: list[str] = ["impersonation", "view-users"]

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
        if path == "/admin/serverinfo":
            return 200, {"themes": {"login": [{"name": n} for n in self.themes]}}
        route = path.removeprefix("/admin/realms/osprey")
        if route == "":
            if verb == "PUT":
                self.realm = {**self.realm, **data}
                return 204, ""
            return 200, dict(self.realm)
        if route.startswith("/clients?clientId="):
            wanted = route.split("=", 1)[1]
            return 200, [c for c in [*self.clients.values(), *self.system_clients] if c["clientId"] == wanted]
        if route == "/clients/cid-conduit/service-account-user":
            return 200, self.service_account
        if route == "/clients/cid-rm/roles":
            return 200, [{"id": f"r-{n}", "name": n} for n in self.realm_management_roles]
        if route == "/users/uid-sa/role-mappings/clients/cid-rm":
            if verb == "GET":
                return 200, [{"id": f"r-{n}", "name": n} for n in self.granted]
            unknown = [r["name"] for r in data if r["name"] not in self.realm_management_roles]
            if unknown:
                return 404, {"error": "Role not found"}
            self.granted += [r["name"] for r in data if r["name"] not in self.granted]
            return 204, ""
        if route.startswith("/clients/cid-") and verb == "DELETE":
            if self.clients.pop(route.rsplit("/", 1)[1], None) is None:
                return 404, {"error": "Could not find client"}
            return 204, ""
        if route.startswith("/clients/cid-") and verb == "PUT":
            self.clients[route.rsplit("/", 1)[1]] = data
            return 204, ""
        if route == "/clients" and verb == "POST":
            if data["clientId"] in {c["clientId"] for c in self.clients.values()}:
                return 409, {"errorMessage": "Client already exists"}
            identifier = f"cid-{len(self.clients) + 1}"
            self.clients[identifier] = {**data, "id": identifier}
            return 201, ""
        if route.startswith("/users?username="):
            wanted = route.split("=", 1)[1].split("&")[0]
            return 200, [u for u in self.users.values() if u["username"] == wanted]
        if route == "/users/profile":
            if verb == "PUT":
                self.unmanaged_attributes = data["unmanagedAttributePolicy"]
                return 200, ""
            return 200, {"attributes": [], "unmanagedAttributePolicy": self.unmanaged_attributes}
        if route == "/users" and verb == "POST":
            if data["username"] in {u["username"] for u in self.users.values()}:
                return 409, {"errorMessage": "User exists with same username"}
            identifier = f"uid-{len(self.users) + 1}"
            stored = {**data, "id": identifier}
            if self.unmanaged_attributes != "ENABLED":
                stored.pop("attributes", None)
            self.users[identifier] = stored
            return 201, ""
        identifier = route.removeprefix("/users/")
        if route.startswith("/users/uid-") and "/" not in identifier and verb == "PUT":
            merged = {**self.users[identifier], **data}
            if self.unmanaged_attributes != "ENABLED":
                merged.pop("attributes", None)
            self.users[identifier] = merged
            return 204, ""
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


def test_registering_adds_the_sign_in_client_and_the_demo_admin_exactly_as_the_realm_renders_them(
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
        if c["clientId"] == HARNESS_CLIENT_ID
    }
    registered = {
        c["clientId"]: {k: v for k, v in c.items() if k != "id"} for c in keycloak.clients.values()
    }
    assert registered == wanted, "the sign-in client, exactly as a fresh apply renders it"

    (admin,) = [u for u in rendered["users"] if u["username"] == DEMO_ADMIN_SUBJECT]
    (created,) = keycloak.users.values()
    assert {k: v for k, v in created.items() if k != "id"} == admin
    assert created["attributes"]["roles"] == DEMO_ADMIN_ROLES


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

    assert len(keycloak.clients) == 1, "the sign-in client once (the launcher's is retired)"
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


def test_the_demo_admin_arrives_with_its_role_even_on_a_realm_that_discards_custom_attributes(
    tmp_path: Path, keycloak: FakeKeycloak
) -> None:
    """Seen on the owner's deployment: signed in as the demo admin and the launcher offered only
    The Glass, because Keycloak had dropped the account's `roles` attribute on creation. A realm
    imported from `realm.json` has custom attributes off until the policy is switched on."""
    env = _env(tmp_path)

    _register(env)

    (admin,) = [u for u in keycloak.users.values() if u["username"] == DEMO_ADMIN_SUBJECT]
    assert admin["attributes"]["roles"] == DEMO_ADMIN_ROLES


def test_a_demo_admin_created_earlier_without_its_role_is_repaired(
    tmp_path: Path, keycloak: FakeKeycloak
) -> None:
    """The same deployment, second run: the account already exists with no roles. 'Already there'
    must not mean 'left as it was' — that is how the missing role would have survived the fix."""
    env = _env(tmp_path)
    keycloak.users["uid-1"] = {"id": "uid-1", "username": DEMO_ADMIN_SUBJECT}

    _register(env)

    assert keycloak.users["uid-1"]["attributes"]["roles"] == DEMO_ADMIN_ROLES


def test_the_sign_in_page_is_restyled_when_keycloak_can_see_the_theme(
    tmp_path: Path, keycloak: FakeKeycloak
) -> None:
    keycloak.themes.append(THEME_NAME)

    lines = _register(_env(tmp_path))

    assert keycloak.realm["loginTheme"] == THEME_NAME
    assert keycloak.realm["displayName"] == DISPLAY_NAME
    assert keycloak.realm["enabled"] is True  # the rest of the realm is carried through
    assert any("sign-in page" in line and "OspreyFlow look" in line for line in lines)


def test_a_theme_keycloak_cannot_see_is_never_named_and_the_next_step_is_said(
    tmp_path: Path, keycloak: FakeKeycloak
) -> None:
    """Naming a theme Keycloak does not have risks a sign-in page that will not render. The
    running Keycloak sees it only after a recreate from a compose file that mounts it."""
    lines = _register(_env(tmp_path))

    assert "loginTheme" not in keycloak.realm
    assert keycloak.realm["displayName"] == DISPLAY_NAME
    (note,) = [line for line in lines if "sign-in page" in line]
    assert "python -m harness.apply" in note


def test_a_demo_admin_that_holds_only_the_admin_role_is_brought_up_to_the_current_set(
    tmp_path: Path, keycloak: FakeKeycloak
) -> None:
    """The state on the owner's Keycloak after the first ruling: the account exists with
    `osprey-admin` alone. Registering again must add the analyst and Studio roles, or the ruling
    would only ever apply to a deployment applied from scratch."""
    keycloak.unmanaged_attributes = "ENABLED"
    keycloak.users["uid-1"] = {
        "id": "uid-1",
        "username": DEMO_ADMIN_SUBJECT,
        "attributes": {"roles": [ADMIN_ROLE]},
    }

    _register(_env(tmp_path))

    assert keycloak.users["uid-1"]["attributes"]["roles"] == DEMO_ADMIN_ROLES


def test_an_existing_client_registered_at_an_old_address_is_brought_to_the_current_one(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Seen when the Admin console moved off port 7000 (macOS's AirPlay Receiver holds it): the
    running realm still registered the old redirect, and Keycloak keeps nothing but what it was
    first given, so signing in to the console would have failed at its own error page. Same class as
    the lost attributes: a rerun must correct what is there, not leave it as it was."""
    env = _env(tmp_path)
    _register(env)
    (identifier,) = [i for i, c in keycloak.clients.items() if c["clientId"] == "osprey-harness"]
    old = "http://localhost:7000/callback"
    keycloak.clients[identifier] = {
        **keycloak.clients[identifier],
        "redirectUris": [old],
        "webOrigins": ["http://localhost:7000"],
        "attributes": {"post.logout.redirect.uris": "http://localhost:7000/", "keep": "me"},
    }

    _register(env)

    now = keycloak.clients[identifier]
    assert now["redirectUris"] == [HARNESS_REDIRECT_URI]
    assert now["webOrigins"] == [HARNESS_ORIGIN]
    assert now["attributes"]["post.logout.redirect.uris"] == f"{HARNESS_ORIGIN}/"
    assert now["attributes"]["keep"] == "me"


def test_a_client_already_at_the_current_address_is_not_rewritten(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    env = _env(tmp_path)
    _register(env)
    writes: list[str] = []
    real = keycloak.clients.__setitem__

    class Watching(dict[str, Any]):
        def __setitem__(self, key: str, value: Any) -> None:
            writes.append(key)
            real(key, value)

    keycloak.clients = Watching(keycloak.clients)
    _register(env)
    assert writes == []


# --- the demo analyst: seen on the owner's deployment, its password stopped working ---


ANALYST_PASSWORD = "the-analysts-own-password"


def test_the_demo_analysts_password_is_made_true_again_after_keycloak_restarts_empty(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Seen: after Keycloak was restarted, the password `deployment.env` names for the demo analyst
    was refused. The realm document carries no credentials, `apply` sets the analyst's password
    through the admin API once, and a restart drops it while the file still names it. Registering
    repaired only the administrator. Catches a registration that leaves the analyst passwordless."""
    env = _env(tmp_path, f"OSPREY_DEMO_ANALYST_PASSWORD={ANALYST_PASSWORD}")

    _register(env)

    assert keycloak.passwords[DEMO_ANALYST_SUBJECT] == ANALYST_PASSWORD


def test_the_analyst_and_the_administrator_keep_their_own_passwords(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Catches a repair that hands one demo account the other's password."""
    env = _env(tmp_path, f"OSPREY_DEMO_ANALYST_PASSWORD={ANALYST_PASSWORD}")
    _register(env)
    assert keycloak.passwords[DEMO_ADMIN_SUBJECT] != ANALYST_PASSWORD
    assert keycloak.passwords[DEMO_ADMIN_SUBJECT] == _env_values(env)["OSPREY_DEMO_ADMIN_PASSWORD"]


def test_a_deployment_applied_without_a_demo_analyst_gets_none(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """Catches a repair that invents an analyst nobody asked for: the env file has no analyst
    password, so there is no account to make true."""
    _register(_env(tmp_path))
    assert DEMO_ANALYST_SUBJECT not in keycloak.passwords
    assert all(u["username"] != DEMO_ANALYST_SUBJECT for u in keycloak.users.values())


def test_the_analyst_password_is_never_printed_or_rewritten(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    env = _env(tmp_path, f"OSPREY_DEMO_ANALYST_PASSWORD={ANALYST_PASSWORD}")
    lines = _register(env)
    assert ANALYST_PASSWORD not in "\n".join(lines)
    assert _env_values(env)["OSPREY_DEMO_ANALYST_PASSWORD"] == ANALYST_PASSWORD


# --- looking an account up, for the seeds' grants (the Conduit's principal id is the subject) ---


def test_an_accounts_subject_is_read_from_keycloak_and_an_unknown_one_is_named(
    keycloak: FakeKeycloak,
) -> None:
    """A grant is written to the identity provider's subject, not the sign-in name, because that is
    what the Conduit's principal id is (`packages/principal_auth`). Catches granting to a name that
    can never match a token, which would leave the demo accounts unable to open their own case."""
    keycloak.users["uid-9"] = {"id": "uid-9", "username": DEMO_ADMIN_SUBJECT}

    found = keycloak_admin.user_id(
        issuer=ISSUER, realm="osprey", token="admin-token", username=DEMO_ADMIN_SUBJECT
    )

    assert found == "uid-9"
    with pytest.raises(RealmConfigurationFailed, match="osprey-nobody"):
        keycloak_admin.user_id(
            issuer=ISSUER, realm="osprey", token="admin-token", username="osprey-nobody"
        )


# --- ADR-112: registration must not undo what an administrator set in People and roles ---


def test_a_role_an_administrator_set_survives_registration_again(keycloak: FakeKeycloak) -> None:
    """Found designing ADR-112 step 3: `make refresh` re-registers the demo accounts, and the
    registration put the rendered attributes back whenever the stored ones differed — so a role
    an administrator set in the Admin area's People and roles was silently reset by the next
    refresh. Registration now restores only an attribute that is missing."""
    keycloak.unmanaged_attributes = "ENABLED"
    rendered = {"username": DEMO_ANALYST_SUBJECT, "attributes": {"roles": ["analyst"], "clearance": ["OFFICIAL"]}}
    assert keycloak_admin.ensure_user(issuer=ISSUER, realm="osprey", token="admin-token", user=rendered) == "created"
    (stored,) = keycloak.users.values()
    stored["attributes"] = {"roles": ["analyst", "reports_viewer"], "clearance": ["OFFICIAL"]}  # the administrator's change
    keycloak_admin.ensure_user(issuer=ISSUER, realm="osprey", token="admin-token", user=rendered)
    assert keycloak.users[stored["id"]]["attributes"]["roles"] == ["analyst", "reports_viewer"]

    del keycloak.users[stored["id"]]["attributes"]["clearance"]  # lost, as when custom attributes were off
    assert keycloak_admin.ensure_user(issuer=ISSUER, realm="osprey", token="admin-token",
                                      user=rendered) == "already there; attributes restored"  # fmt: skip
    assert keycloak.users[stored["id"]]["attributes"] == {"roles": ["analyst", "reports_viewer"], "clearance": ["OFFICIAL"]}


def test_a_refresh_grants_the_conduits_account_the_roles_it_lacks(tmp_path: Path, keycloak: FakeKeycloak) -> None:
    """Found live, 11 October 2026: the deployment's Conduit held only `impersonation` and
    `view-users` — grants are made at apply, and `make refresh` never revisited them, so the Admin
    area's People and roles and Dashboards would have been refused on any existing deployment."""
    lines = _register(_env(tmp_path))
    assert "the Conduit's account granted manage-clients, manage-users" in lines
    assert sorted(keycloak.granted) == ["impersonation", "manage-clients", "manage-users", "view-users"]
    assert "realm-admin" not in keycloak.granted
    assert "the Conduit's account already holds its roles" in _register(_env(tmp_path))


def test_superset_gets_its_sign_in_client_only_when_it_is_configured(tmp_path: Path, keycloak: FakeKeycloak) -> None:
    """ADR-111 Amendment 2: Superset signs people in through the deployment's identity provider —
    a confidential client whose secret comes from the env file and whose only redirect is
    Superset's own address. A deployment without Superset gets no such client."""
    _register(_env(tmp_path))
    assert "osprey-superset" not in {c["clientId"] for c in keycloak.clients.values()}

    lines = _register(_env(tmp_path, "SUPERSET_OIDC_CLIENT_SECRET=superset-secret",
                           "SUPERSET_PUBLIC_ORIGIN=http://localhost:8088"))  # fmt: skip
    (client,) = [c for c in keycloak.clients.values() if c["clientId"] == "osprey-superset"]
    assert client["publicClient"] is False and client["secret"] == "superset-secret"
    assert client["redirectUris"] == ["http://localhost:8088/oauth-authorized/keycloak"]
    assert "roles" in {m["name"] for m in client["protocolMappers"]}
    assert any(line.startswith("sign-in client osprey-superset") for line in lines)
    assert "superset-secret" not in "\n".join(lines), "a secret is never printed"


# --- ADR-113 decision 8: four distinct demo personas ---


def test_a_demonstration_deployment_gets_the_engineer_and_the_report_viewer_with_their_own_passwords(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    from harness.realm import DEMO_ENGINEER_SUBJECT, DEMO_REPORT_VIEWER_SUBJECT

    keycloak.unmanaged_attributes = "ENABLED"
    env = _env(tmp_path, "OSPREY_DEMO_ANALYST_PASSWORD=analyst-pass")
    _register(env)
    values = _env_values(env)
    by_name = {u["username"]: u for u in keycloak.users.values()}
    assert by_name[DEMO_ENGINEER_SUBJECT]["attributes"]["roles"] == ["data_engineer"]
    assert by_name[DEMO_REPORT_VIEWER_SUBJECT]["attributes"]["roles"] == ["reports_viewer"]
    assert keycloak.passwords[DEMO_ENGINEER_SUBJECT] == values["OSPREY_DEMO_ENGINEER_PASSWORD"]
    assert keycloak.passwords[DEMO_REPORT_VIEWER_SUBJECT] == values["OSPREY_DEMO_REPORT_VIEWER_PASSWORD"]
    _register(env)
    assert _env_values(env)["OSPREY_DEMO_ENGINEER_PASSWORD"] == values["OSPREY_DEMO_ENGINEER_PASSWORD"], "kept, never rotated"


def test_a_deployment_without_a_demo_analyst_gets_no_further_personas(keycloak: FakeKeycloak, tmp_path: Path) -> None:
    env = _env(tmp_path)
    _register(env)
    assert "OSPREY_DEMO_ENGINEER_PASSWORD" not in _env_values(env)
    assert {u["username"] for u in keycloak.users.values()} == {DEMO_ADMIN_SUBJECT}


def test_the_analysts_data_engineer_role_is_withdrawn_and_nothing_else_is(keycloak: FakeKeycloak, tmp_path: Path) -> None:
    """The one removal registration makes is a ruling's; a role an administrator added in the Admin
    area stays, so a refresh still never undoes their change."""
    keycloak.unmanaged_attributes = "ENABLED"
    keycloak.users["uid-a"] = {"id": "uid-a", "username": DEMO_ANALYST_SUBJECT,
                               "attributes": {"roles": ["analyst", "data_engineer", "right:read_export_ledger"],
                                              "clearance": ["OFFICIAL"]}}  # fmt: skip
    env = _env(tmp_path, "OSPREY_DEMO_ANALYST_PASSWORD=analyst-pass")
    lines = _register(env)
    assert keycloak.users["uid-a"]["attributes"]["roles"] == ["analyst", "right:read_export_ledger"]
    assert any("withdrew data_engineer" in line for line in lines)
    admin = next(u for u in keycloak.users.values() if u["username"] == DEMO_ADMIN_SUBJECT)
    assert "data_engineer" in admin["attributes"]["roles"], "the admin keeps every surface"


def test_a_retired_launcher_client_is_removed_and_its_absence_is_fine(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """ADR-114 Amendment 5: Keycloak keeps its realm across restarts now, so the launcher's client a
    deployment registered before B2d would stay — a loopback redirect nothing uses. Registration
    removes it, and says nothing is wrong when it was never there."""
    keycloak.clients["cid-old"] = {"clientId": "osprey-launcher", "id": "cid-old"}
    lines = _register(_env(tmp_path))
    assert "osprey-launcher" not in {c["clientId"] for c in keycloak.clients.values()}
    assert any("osprey-launcher" in line and "removed" in line for line in lines)
    again = _register(_env(tmp_path))
    assert any("osprey-launcher" in line and "not present" in line for line in again)
