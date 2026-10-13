"""A cloud deployment's first administrator, by one-time code (ADR-114 Amendment 10 point 4).

The account and its code are checked against a real Keycloak — the deployment's own image, a
throwaway container named by `OSPREY_TEST_KEYCLOAK_CONTAINER`, reached at `OSPREY_TEST_KEYCLOAK`
with its bootstrap admin `admin` / `OSPREY_TEST_KEYCLOAK_PASSWORD` — through the same `kcadm.sh`
inside the container the install uses: Keycloak keeps only the attributes its user profile allows,
and only it can say whether the code is the account's password.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from typing import Any

import pytest
from harness import first_admin
from harness.keycloak_admin import _call, admin_token, ensure_unmanaged_attributes
from ontology.handling import load_uk_le_scheme
from services.api import identity_admin


def test_the_code_has_an_invitations_shape() -> None:
    assert first_admin.CODE_ALPHABET == identity_admin.CODE_ALPHABET
    assert re.fullmatch(r"([A-HJ-NP-Z2-9]{4}-){3}[A-HJ-NP-Z2-9]{4}", first_admin.one_time_code())


def test_the_first_administrator_holds_the_top_clearance_and_must_choose_a_password() -> None:
    user = first_admin.first_administrator("admin", code="ABCD", scheme=load_uk_le_scheme())
    assert user["attributes"]["roles"] == ["osprey-admin"]
    assert user["attributes"]["clearance"] == ["SECRET"]
    assert user["requiredActions"] == ["UPDATE_PASSWORD"]
    assert user["credentials"] == [{"type": "password", "value": "ABCD", "temporary": True}]


KEYCLOAK = os.environ.get("OSPREY_TEST_KEYCLOAK")
CONTAINER = os.environ.get("OSPREY_TEST_KEYCLOAK_CONTAINER", "")
live = pytest.mark.skipif(not KEYCLOAK, reason="needs OSPREY_TEST_KEYCLOAK, a throwaway Keycloak")


def _create(realm: str) -> str:
    return first_admin.create_first_administrator(["docker", "exec"], keycloak=CONTAINER,
                                                  realm=realm)  # fmt: skip


@pytest.fixture
def realm() -> Any:
    assert KEYCLOAK is not None
    token = admin_token(issuer=KEYCLOAK, admin_user="admin",
                        admin_password=os.environ["OSPREY_TEST_KEYCLOAK_PASSWORD"])  # fmt: skip
    name = f"first-admin-{uuid.uuid4().hex[:8]}"
    status, _ = _call(f"{KEYCLOAK}/admin/realms", token=token,
                      data={"realm": name, "enabled": True})  # fmt: skip
    assert status == 201
    ensure_unmanaged_attributes(issuer=KEYCLOAK, realm=name, token=token)
    _call(f"{KEYCLOAK}/admin/realms/{name}/clients", token=token,
          data={"clientId": "probe", "publicClient": True,
                "directAccessGrantsEnabled": True})  # fmt: skip
    yield name, token
    _call(f"{KEYCLOAK}/admin/realms/{name}", token=token, method="DELETE")


def _sign_in(realm: str, username: str, password: str) -> dict[str, Any]:
    data = urllib.parse.urlencode({"client_id": "probe", "grant_type": "password",
                                   "username": username, "password": password}).encode()  # fmt: skip
    request = urllib.request.Request(
        f"{KEYCLOAK}/realms/{realm}/protocol/openid-connect/token", data=data
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())  # type: ignore[no-any-return]
    except urllib.error.HTTPError as error:
        return json.loads(error.read())  # type: ignore[no-any-return]


@live
def test_the_code_is_the_accounts_password_until_it_chooses_its_own(realm: Any) -> None:
    name, token = realm
    code = _create(name)
    status, users = _call(f"{KEYCLOAK}/admin/realms/{name}/users?username=admin&exact=true",
                          token=token)  # fmt: skip
    (user,) = users
    assert user["attributes"]["roles"] == ["osprey-admin"]
    assert user["attributes"]["clearance"] == ["SECRET"]
    assert user["requiredActions"] == ["UPDATE_PASSWORD"]
    # The right code reaches the update-password step; a wrong one is refused as a wrong password.
    assert _sign_in(name, "admin", code)["error_description"] == "Account is not fully set up"
    assert _sign_in(name, "admin", "WRONG-CODE")["error_description"] == "Invalid user credentials"


@live
def test_an_existing_account_is_never_replaced(realm: Any) -> None:
    name, _ = realm
    _create(name)
    with pytest.raises(first_admin.FirstAdministratorRefused, match="was not changed"):
        _create(name)
