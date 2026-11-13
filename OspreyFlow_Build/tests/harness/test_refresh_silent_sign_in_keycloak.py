"""A refresh keeps the person signed in: the Glass's silent `prompt=none` round at load, against a
real Keycloak (`06_DECISIONS.md` ADR-050 Amendment 3).

Rule 15: the fake identity provider in `apps/workspace/keyboard/refresh-sign-in.spec.ts` and
`src/auth/signInAtLoad.test.ts` answers `prompt=none` with `error=login_required` when it has no
session, and with a code when it has one. This measures both against the real thing, Keycloak 26.0
(the deployment's pinned image) running the **rendered** realm (`harness.realm.render_realm_json`),
with the Glass's own client (`osprey-glass`, public, PKCE S256, the root as its one redirect):

- no session: Keycloak refuses the round, `error=login_required` on the redirect, no code and no
  login page (what the Glass turns into its Sign in screen);
- a session (the person signed in once through Keycloak's own form): the same request is answered
  with a code, which the token endpoint exchanges, without a password asked (a refresh signed in);
- after the session is ended (Keycloak's logout), the refusal is back.

The browser is scripted with httpx, as `test_organisation_sign_in.py` scripts it. One throwaway
container on a free high port of 127.0.0.1, removed afterwards; nothing here reaches 8080, 8081 or
any deployment of this machine. The lane stacks carry no Keycloak, so this is the "live case
against a real Keycloak": it runs wherever `make test` runs docker (the test server).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from harness import keycloak_admin
from harness.realm import GLASS_CLIENT_ID, render_realm_json
from tools.layout import CORE

from schemas.deployment import OspreyConfig

from .tls_fixtures import docker

KEYCLOAK_IMAGE = "quay.io/keycloak/keycloak:26.0"
REALM = "osprey"
PERSON = {"username": "refresh.person", "password": "a-throwaway-password-1"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class Keycloak:
    name: str
    origin: str
    admin_password: str
    #: The Glass's redirect, as the rendered realm registers it.
    redirect_uri: str


@pytest.fixture(scope="module")
def keycloak(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Keycloak]:
    folder: Path = tmp_path_factory.mktemp("refresh-keycloak")
    realm = json.loads(
        render_realm_json(OspreyConfig.model_validate({"profile": "local-lite"}), realm_name=REALM)
    )
    glass = next(c for c in realm["clients"] if c["clientId"] == GLASS_CLIENT_ID)
    realm_file = folder / "realm.json"
    realm_file.write_text(json.dumps(realm), encoding="utf-8")
    realm_file.chmod(0o644)

    name = f"osprey-test-refresh-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    password = secrets.token_urlsafe(16)
    docker(
        "run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:8080",
        "-e", "KC_BOOTSTRAP_ADMIN_USERNAME=admin", "-e", f"KC_BOOTSTRAP_ADMIN_PASSWORD={password}",
        "-v", f"{realm_file}:/opt/keycloak/data/import/realm.json:ro",
        KEYCLOAK_IMAGE, "start-dev", "--import-realm", f"--hostname=http://localhost:{port}",
    )  # fmt: skip
    origin = f"http://localhost:{port}"
    try:
        deadline = time.monotonic() + 180
        while True:
            try:
                with urllib.request.urlopen(
                    f"{origin}/realms/{REALM}/.well-known/openid-configuration", timeout=5
                ) as r:
                    if r.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() > deadline:
                logs = docker("logs", name, check=False)
                raise AssertionError(
                    f"Keycloak never became ready:\n{(logs.stdout + logs.stderr)[-3000:]}"
                )
            time.sleep(2)
        token = keycloak_admin.admin_token(
            issuer=origin, admin_user="admin", admin_password=password
        )
        status, body = keycloak_admin._call(
            f"{origin}/admin/realms/{REALM}/users", token=token,
            data={"username": PERSON["username"], "enabled": True, "emailVerified": True,
                  "firstName": "Refresh", "lastName": "Person",
                  "email": "refresh.person@example.invalid",
                  "credentials": [{"type": "password", "value": PERSON["password"],
                                   "temporary": False}]},
        )  # fmt: skip
        assert status == 201, (status, body)
        yield Keycloak(name, origin, password, glass["redirectUris"][0])
    finally:
        docker("rm", "-f", "-v", name, check=False)


#: The silent round exactly as `oidc-client-ts` sends it, captured and held by
#: `apps/workspace/keyboard/refresh-sign-in.spec.ts` (which fails when the library's request
#: changes): its fixed parameters, and the names of the two it makes afresh each time.
SILENT_ROUND = json.loads(
    (CORE / "apps/workspace/keyboard/fixtures/silent-round-request.json").read_text(
        encoding="utf-8"
    )
)


def _authorise(kc: Keycloak, *, prompt_none: bool) -> tuple[dict[str, str], str]:
    """The Glass's authorisation request, from the captured silent round: its parameters and the
    PKCE verifier. Without `prompt_none`, the same request less `prompt` (the interactive
    sign-in)."""
    assert sorted(SILENT_ROUND["random"]) == ["code_challenge", "state"], SILENT_ROUND
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    params = {
        k: (kc.redirect_uri if v == "<origin>/" else v) for k, v in SILENT_ROUND["fixed"].items()
    }
    assert params["prompt"] == "none" and params["redirect_uri"] == kc.redirect_uri
    params |= {"state": secrets.token_urlsafe(8), "code_challenge": challenge}
    if not prompt_none:
        del params["prompt"]
    return params, verifier


def _answer(location: str) -> dict[str, str]:
    return {
        k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(location).query).items()
    }


def _silent_round(kc: Keycloak, browser: httpx.Client) -> tuple[httpx.Response, str]:
    params, _ = _authorise(kc, prompt_none=True)
    path = f"{kc.origin}/realms/{REALM}{SILENT_ROUND['path']}"
    return browser.get(path, params=params), params["state"]


def _sign_in_through_the_form(kc: Keycloak, browser: httpx.Client) -> None:
    params, _ = _authorise(kc, prompt_none=False)
    page = browser.get(f"{kc.origin}/realms/{REALM}/protocol/openid-connect/auth", params=params)
    assert page.status_code == 200, page.status_code
    # Keycloak marks its cookies Secure even over plain HTTP in start-dev; a browser sends them to
    # localhost (a secure context), http.cookiejar does not (`test_phase8_exit_over_the_wire.py`).
    for cookie in browser.cookies.jar:
        cookie.secure = False
    action = re.search(r'action="([^"]+)"', page.text)
    assert action, "Keycloak's login page carried no form action"
    done = browser.post(action.group(1).replace("&amp;", "&"), data=PERSON)
    assert done.status_code == 302, done.status_code
    for cookie in browser.cookies.jar:
        cookie.secure = False


def test_with_no_session_keycloak_refuses_prompt_none_with_login_required(
    keycloak: Keycloak,
) -> None:
    with httpx.Client(follow_redirects=False, timeout=30) as browser:
        answered, state = _silent_round(keycloak, browser)
    assert answered.status_code == 302, answered.status_code
    location = answered.headers["location"]
    assert location.startswith(keycloak.redirect_uri), location
    back = _answer(location)
    assert back.get("error") == "login_required", back
    assert "code" not in back, back
    # The library matches the refusal to its request by `state`; Keycloak 26 also names itself.
    assert back.get("state") == state, back
    assert back.get("iss") == f"{keycloak.origin}/realms/{REALM}", back


def test_with_a_session_the_silent_round_signs_in_without_a_password_then_refuses_after_logout(
    keycloak: Keycloak,
) -> None:
    with httpx.Client(follow_redirects=False, timeout=30) as browser:
        _sign_in_through_the_form(keycloak, browser)

        # The refresh: a new authorisation request, prompt=none, the same browser's cookies.
        params, verifier = _authorise(keycloak, prompt_none=True)
        answered = browser.get(
            f"{keycloak.origin}/realms/{REALM}/protocol/openid-connect/auth", params=params
        )
        assert answered.status_code == 302, answered.status_code
        back = _answer(answered.headers["location"])
        assert "error" not in back, back
        assert back.get("state") == params["state"]
        assert back.get("iss") == f"{keycloak.origin}/realms/{REALM}", back
        exchanged = browser.post(
            f"{keycloak.origin}/realms/{REALM}/protocol/openid-connect/token",
            data={"grant_type": "authorization_code", "client_id": GLASS_CLIENT_ID,
                  "code": back["code"],
                  "redirect_uri": keycloak.redirect_uri, "code_verifier": verifier},
        )  # fmt: skip
        assert exchanged.status_code == 200, exchanged.text
        tokens = exchanged.json()
        assert tokens["access_token"] and tokens["id_token"]
        # ADR-050 Amendment 2: still no refresh token; the round above is the only renewal.
        assert "refresh_token" not in tokens, sorted(tokens)

        # The session ended at the provider: the refusal is back, and the Glass shows its screen.
        logout = browser.post(
            f"{keycloak.origin}/realms/{REALM}/protocol/openid-connect/logout",
            data={"client_id": GLASS_CLIENT_ID, "id_token_hint": tokens["id_token"]},
        )
        assert logout.status_code in (200, 204, 302), logout.status_code
        for cookie in browser.cookies.jar:
            cookie.secure = False
        refused, state = _silent_round(keycloak, browser)
        assert refused.status_code == 302
        again = _answer(refused.headers["location"])
        assert again.get("error") == "login_required" and again.get("state") == state, again
