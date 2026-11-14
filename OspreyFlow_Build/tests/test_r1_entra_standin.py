"""R1's Entra ID stand-in signs (v0.5.2, step 8): `process/lanes/platform/gates/r1_kind_servers.py entra`
serves `/token` (authorization_code and client_credentials) and a one-user `/authorize`, signing with a
key it makes at start and never writes out, as Entra signs with its own (`ENTRA_STANDIN.md`).

Each case runs the stand-in on loopback over plain HTTP (its TLS is kind's; the protocol is the same)
and talks to it as Superset, the Glass and the report sync will: real HTTP, real JWTs.

**It refuses what Entra refuses on those paths (rule 15)**, each with Entra's own error and AADSTS code:
another tenant (AADSTS90002), an unknown client (AADSTS700016), a redirect URI not registered (AADSTS50011,
never redirected to), a scope the client was not granted, so no `scp` (AADSTS65001), a wrong or missing
secret (AADSTS7000215, AADSTS7000218), a code used twice or by another client or redirect (AADSTS70008,
AADSTS70000), a PKCE verifier that does not match (AADSTS50148), a client-credentials scope that is not
`<resource>/.default` (AADSTS1002012) or names another resource (AADSTS500011), and a grant it does not
know (AADSTS70003).

**And what it grants passes the Conduit's real resolver** (`services.api.auth.PrincipalResolver`, with
the poc render's own issuer, audience and claim mapping, its keys read from the stand-in's own JWKS):
`test_a_glass_sign_in_by_code_and_pkce_is_the_conduits_person`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
from principal_auth import ClaimMapping
from services.api.auth import PrincipalResolver
from services.api.config import ApiConfig

from tests.harness.test_cloud_platform_render import _config, _values
from tests.services.api.test_auth import _config as _api_config
from tests.services.api.test_auth_entra_claims import FakePeople

SERVERS = Path(__file__).parents[1] / "process/lanes/platform/gates/r1_kind_servers.py"

TENANT = "00000000-1111-4222-8333-444444444444"
GLASS = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
API = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
SUPERSET = "cccccccc-dddd-4eee-8fff-000000000001"
REPORTS = "dddddddd-eeee-4fff-8000-000000000002"
ADMIN = "50000000-0000-4000-8000-000000000001"
CLEARANCE = "extension_0123456789abcdef0123456789abcdef_clearance"
GLASS_REDIRECT = "https://osprey.r1.test/"
SUPERSET_REDIRECT = "https://bi.osprey.r1.test/oauth-authorized/entra"
SUPERSET_SECRET = "superset-throwaway-secret"
REPORTS_SECRET = "reports-throwaway-secret"
ACCESS = f"api://{API}/access_as_user"

CONFIG: dict[str, Any] = {
    "tenant_id": TENANT,
    "jwks": [],  # the driver's own key, for its crafted refusals (none here)
    "api": {"app_id": API, "identifier": f"api://{API}", "scopes": ["access_as_user"]},
    "clients": {
        GLASS: {"redirect_uris": [GLASS_REDIRECT], "delegated": ["access_as_user"]},
        SUPERSET: {"secret": SUPERSET_SECRET, "redirect_uris": [SUPERSET_REDIRECT],
                   "delegated": ["access_as_user"]},
        REPORTS: {"secret": REPORTS_SECRET, "service_principal": "60000000-0000-4000-8000-000000000002",
                  "roles": ["Reports.Read"]},
    },
    "user": {
        "oid": ADMIN, "name": "Synthetic Administrator", "preferred_username": "admin@r1.test",
        "claims": {CLEARANCE: "OFFICIAL-SENSITIVE",
                   "groups": ["20000000-0000-4000-8000-000000000001",
                              "30000000-0000-4000-8000-000000000001"]},
    },
}  # fmt: skip


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("r1_kind_servers", SERVERS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def standin() -> Iterator[str]:
    server = _module().make_server("entra", CONFIG, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _get(url: str) -> tuple[int, dict[str, str], str]:
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url) as answer:
            return answer.status, dict(answer.headers), answer.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode()


def _post(url: str, form: dict[str, str], basic: tuple[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    if basic:
        request.add_header("Authorization", "Basic " + base64.b64encode(":".join(basic).encode()).decode())
    try:
        with urllib.request.urlopen(request) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _authorize(base: str, client: str, redirect: str, scope: str, challenge: str | None = None,
               tenant: str = TENANT) -> tuple[int, dict[str, str], str]:  # fmt: skip
    query = {"client_id": client, "response_type": "code", "redirect_uri": redirect, "scope": scope,
             "state": "s-1", "nonce": "n-1"}  # fmt: skip
    if challenge:
        query |= {"code_challenge": challenge, "code_challenge_method": "S256"}
    return _get(f"{base}/{tenant}/oauth2/v2.0/authorize?{urllib.parse.urlencode(query)}")


def _code(location: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(location).query))


def _token_url(base: str, tenant: str = TENANT) -> str:
    return f"{base}/{tenant}/oauth2/v2.0/token"


def _keys(base: str) -> dict[str, Any]:
    return json.loads(_get(f"{base}/{TENANT}/discovery/v2.0/keys")[2])


def _verify(base: str, token: str, audience: str) -> dict[str, Any]:
    keys = {k["kid"]: jwt.PyJWK(k) for k in _keys(base)["keys"]}
    kid = jwt.get_unverified_header(token)["kid"]
    return jwt.decode(token, keys[kid].key, algorithms=["RS256"], audience=audience,
                      issuer=f"https://login.microsoftonline.com/{TENANT}/v2.0")  # fmt: skip


def _glass_code(base: str) -> tuple[str, str]:
    verifier, challenge = _pkce()
    status, headers, _ = _authorize(base, GLASS, GLASS_REDIRECT, f"openid profile {ACCESS}", challenge)
    assert status == 302, status
    returned = _code(headers["Location"])
    assert returned["state"] == "s-1" and headers["Location"].startswith(GLASS_REDIRECT)
    return returned["code"], verifier


# ---- the key ------------------------------------------------------------------------------------


def test_the_key_is_made_at_start_and_never_the_same_twice(standin: str) -> None:
    first = {k["kid"] for k in _keys(standin)["keys"]}
    assert len(first) == 1 and all(k["kty"] == "RSA" and k["alg"] == "RS256" for k in _keys(standin)["keys"])
    other = _module().make_server("entra", CONFIG, "127.0.0.1", 0)
    try:
        assert {k["kid"] for k in other.RequestHandlerClass.keys_document["keys"]} != first  # type: ignore[attr-defined]
    finally:
        other.server_close()
    discovery = json.loads(_get(f"{standin}/{TENANT}/v2.0/.well-known/openid-configuration")[2])
    assert discovery["token_endpoint"].endswith(f"/{TENANT}/oauth2/v2.0/token")
    assert discovery["authorization_endpoint"].endswith(f"/{TENANT}/oauth2/v2.0/authorize")


# ---- authorization code -------------------------------------------------------------------------


def test_a_glass_sign_in_by_code_and_pkce_is_the_conduits_person(
    standin: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, verifier = _glass_code(standin)
    status, answer = _post(_token_url(standin), {
        "grant_type": "authorization_code", "client_id": GLASS, "code": code,
        "redirect_uri": GLASS_REDIRECT, "code_verifier": verifier, "scope": f"openid profile {ACCESS}",
    })  # fmt: skip
    assert status == 200, answer
    assert answer["token_type"] == "Bearer" and answer["expires_in"] > 0
    access = _verify(standin, answer["access_token"], API)
    assert (access["tid"], access["oid"], access["azp"], access["scp"], access["ver"]) == (
        TENANT, ADMIN, GLASS, "access_as_user", "2.0")  # fmt: skip
    assert access[CLEARANCE] == "OFFICIAL-SENSITIVE" and "idtyp" not in access
    identity = _verify(standin, answer["id_token"], GLASS)
    assert identity["nonce"] == "n-1" and identity["oid"] == ADMIN
    # Through the Conduit's own resolver, as the poc render configures it.
    environment = _values(_config("poc"))["environment"]
    monkeypatch.setenv("OSPREY_CLAIM_MAPPING", environment["OSPREY_CLAIM_MAPPING"])
    config: ApiConfig = _api_config(
        f"{standin}/{TENANT}/discovery/v2.0/keys",
        oidc_issuer=environment["OIDC_ISSUER"],
        oidc_audience=environment["OIDC_AUDIENCE"],
    )
    resolver = PrincipalResolver(config, claim_mapping=ClaimMapping.from_env(), role_source=FakePeople())
    principal = asyncio.run(resolver.resolve_principal(answer["access_token"]))
    assert (principal.id, principal.org_unit, principal.clearance) == (ADMIN, "unit-1", "OFFICIAL-SENSITIVE")


def test_superset_signs_in_as_a_confidential_client_with_its_secret(standin: str) -> None:
    status, headers, _ = _authorize(standin, SUPERSET, SUPERSET_REDIRECT, f"openid profile email {ACCESS}")
    code = _code(headers["Location"])["code"]
    form = {"grant_type": "authorization_code", "client_id": SUPERSET, "code": code,
            "redirect_uri": SUPERSET_REDIRECT}  # fmt: skip
    status, answer = _post(_token_url(standin), form)
    assert (status, answer["error"]) == (401, "invalid_client") and "AADSTS7000218" in answer["error_description"]
    status, answer = _post(_token_url(standin), {**form, "client_secret": "wrong"})
    assert (status, answer["error"]) == (401, "invalid_client") and "AADSTS7000215" in answer["error_description"]
    # The code was not spent by a refused client: the right secret, by HTTP Basic, still takes it.
    status, answer = _post(_token_url(standin), form, basic=(SUPERSET, SUPERSET_SECRET))
    assert status == 200, answer
    access = _verify(standin, answer["access_token"], API)
    assert (access["azp"], access["scp"], access["oid"]) == (SUPERSET, "access_as_user", ADMIN)


def test_a_code_is_spent_once_by_its_own_client_redirect_and_verifier(standin: str) -> None:
    code, verifier = _glass_code(standin)
    good = {"grant_type": "authorization_code", "client_id": GLASS, "code": code,
            "redirect_uri": GLASS_REDIRECT, "code_verifier": verifier}  # fmt: skip
    for change, aadsts in [
        ({"code_verifier": "not-the-verifier-" + "x" * 30}, "AADSTS50148"),
        ({"redirect_uri": "https://elsewhere.test/"}, "AADSTS70000"),
        ({"client_id": SUPERSET, "client_secret": SUPERSET_SECRET}, "AADSTS70000"),
        ({"code": "never-issued"}, "AADSTS70008"),
    ]:
        status, answer = _post(_token_url(standin), {**good, **change})
        assert (status, answer["error"]) == (400, "invalid_grant"), (change, answer)
        assert aadsts in answer["error_description"], (change, answer)
    assert _post(_token_url(standin), good)[0] == 200
    status, answer = _post(_token_url(standin), good)
    assert (status, answer["error"]) == (400, "invalid_grant") and "AADSTS70008" in answer["error_description"]


def test_authorize_refuses_another_tenant_client_redirect_and_an_ungranted_scope(standin: str) -> None:
    status, headers, body = _authorize(standin, GLASS, GLASS_REDIRECT, ACCESS, tenant="ffffffff-0000-4000-8000-000000000000")
    assert status == 400 and "AADSTS90002" in body and "Location" not in headers
    status, headers, body = _authorize(standin, "eeeeeeee-0000-4000-8000-000000000009", GLASS_REDIRECT, ACCESS)
    assert status == 400 and "AADSTS700016" in body and "Location" not in headers
    status, headers, body = _authorize(standin, GLASS, "https://attacker.test/", ACCESS)
    assert status == 400 and "AADSTS50011" in body and "Location" not in headers
    # The report sync's registration was granted no delegated scope: no scp to give, so refused.
    reports = {**CONFIG["clients"][REPORTS], "redirect_uris": [GLASS_REDIRECT]}
    CONFIG["clients"]["eeeeeeee-0000-4000-8000-000000000010"] = reports
    try:
        status, headers, _ = _authorize(standin, "eeeeeeee-0000-4000-8000-000000000010", GLASS_REDIRECT, ACCESS)
    finally:
        del CONFIG["clients"]["eeeeeeee-0000-4000-8000-000000000010"]
    returned = _code(headers.get("Location", ""))
    assert status == 302 and returned.get("error") == "consent_required", (status, headers)
    assert "AADSTS65001" in returned["error_description"] and "code" not in returned
    # Another tenant at the token endpoint too.
    status, answer = _post(_token_url(standin, "ffffffff-0000-4000-8000-000000000000"),
                           {"grant_type": "client_credentials", "client_id": REPORTS})  # fmt: skip
    assert status == 400 and "AADSTS90002" in answer["error_description"]


# ---- client credentials -------------------------------------------------------------------------


def test_the_report_sync_gets_an_app_only_token_with_its_roles_and_no_scp(standin: str) -> None:
    status, answer = _post(_token_url(standin), {
        "grant_type": "client_credentials", "client_id": REPORTS, "client_secret": REPORTS_SECRET,
        "scope": f"api://{API}/.default",
    })  # fmt: skip
    assert status == 200, answer
    claims = _verify(standin, answer["access_token"], API)
    assert claims["idtyp"] == "app" and "scp" not in claims
    assert claims["roles"] == ["Reports.Read"] and claims["azp"] == REPORTS
    assert claims["oid"] == claims["sub"] == "60000000-0000-4000-8000-000000000002"
    assert "id_token" not in answer


@pytest.mark.parametrize(
    ("form", "status", "error", "aadsts"),
    [
        ({"client_secret": "wrong"}, 401, "invalid_client", "AADSTS7000215"),
        ({"client_id": "eeeeeeee-0000-4000-8000-000000000009"}, 400, "invalid_client", "AADSTS700016"),
        ({"client_id": GLASS, "client_secret": ""}, 401, "invalid_client", "AADSTS7000218"),
        ({"scope": f"api://{API}/access_as_user"}, 400, "invalid_scope", "AADSTS1002012"),
        ({"scope": "api://ffffffff-0000-4000-8000-000000000000/.default"}, 400, "invalid_resource", "AADSTS500011"),
        ({"grant_type": "password"}, 400, "unsupported_grant_type", "AADSTS70003"),
    ],
)  # fmt: skip
def test_client_credentials_are_refused_as_entra_refuses_them(
    standin: str, form: dict[str, str], status: int, error: str, aadsts: str
) -> None:
    good = {"grant_type": "client_credentials", "client_id": REPORTS, "client_secret": REPORTS_SECRET,
            "scope": f"api://{API}/.default"}  # fmt: skip
    got, answer = _post(_token_url(standin), {**good, **form})
    assert (got, answer["error"]) == (status, error), answer
    assert aadsts in answer["error_description"]
    assert "error_codes" in answer and "timestamp" in answer


# ---- the record of what was granted (case-b's install test reads it) ------------------------------


def test_each_grant_is_logged_once_and_no_refusal_is(standin: str, capfd: pytest.CaptureFixture[str]) -> None:
    """`kubectl logs deployment/entra-standin` is how v052-r1's verifier sees which registrations
    were used: one line per token issued, exactly `entra-standin: granted <grant_type>
    client=<client_id> audience=<aud>`, and none of that form for a refused request."""
    capfd.readouterr()
    good = {"grant_type": "client_credentials", "client_id": REPORTS, "client_secret": REPORTS_SECRET,
            "scope": f"api://{API}/.default"}  # fmt: skip
    assert _post(_token_url(standin), good)[0] == 200
    assert _post(_token_url(standin), {**good, "client_secret": "wrong"})[0] == 401
    code, verifier = _glass_code(standin)
    assert _post(_token_url(standin), {
        "grant_type": "authorization_code", "client_id": GLASS, "code": code,
        "redirect_uri": GLASS_REDIRECT, "code_verifier": verifier,
    })[0] == 200  # fmt: skip
    assert _post(_token_url(standin), {"grant_type": "authorization_code", "client_id": GLASS,
                                       "code": "spent", "redirect_uri": GLASS_REDIRECT})[0] == 400  # fmt: skip
    granted = [line for line in capfd.readouterr().err.splitlines() if " granted " in line]
    assert granted == [
        f"entra-standin: granted client_credentials client={REPORTS} audience={API}",
        f"entra-standin: granted authorization_code client={GLASS} audience={API}",
    ]


# ---- several people, by login_hint (platform-b's v052-r1 dashboards check) ----------------

READER = "50000000-0000-4000-8000-0000000000b1"
GROUPS = ["20000000-0000-4000-8000-000000000001", "30000000-0000-4000-8000-000000000001"]
PEOPLE = {**CONFIG, "users": [
    CONFIG["user"],
    {"oid": READER, "name": "Synthetic Reader", "preferred_username": "reader@r1.test",
     "claims": {CLEARANCE: "OFFICIAL-SENSITIVE", "groups": GROUPS}},
]}  # fmt: skip


@pytest.fixture
def people() -> Iterator[str]:
    server = _module().make_server("entra", PEOPLE, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _superset_token(base: str, hint: str | None) -> tuple[int, dict[str, Any]]:
    query = {"client_id": SUPERSET, "response_type": "code", "redirect_uri": SUPERSET_REDIRECT,
             "scope": f"openid profile email {ACCESS}", "state": "s-1", "nonce": "n-1"}  # fmt: skip
    if hint is not None:
        query["login_hint"] = hint
    url = f"{base}/{TENANT}/oauth2/v2.0/authorize?{urllib.parse.urlencode(query)}"
    status, headers, body = _get(url)
    if status != 302:
        return status, {"page": body}
    code = _code(headers["Location"])["code"]
    form = {"grant_type": "authorization_code", "client_id": SUPERSET, "code": code,
            "redirect_uri": SUPERSET_REDIRECT}  # fmt: skip
    return _post(_token_url(base), form, basic=(SUPERSET, SUPERSET_SECRET))


@pytest.mark.parametrize(
    ("hint", "oid"),
    [
        (None, ADMIN),
        ("admin@r1.test", ADMIN),
        ("reader@r1.test", READER),
        ("Reader@R1.test", READER),
    ],
)
def test_the_person_signed_in_is_the_one_the_hint_names(
    people: str, hint: str | None, oid: str
) -> None:
    """Entra accepts `login_hint` on /authorize: the stand-in signs in the person whose username it
    names (no hint: the first, as before), and the code carries that person to the token, the
    access token's and the identity token's `oid` theirs, never the first's."""
    status, answer = _superset_token(people, hint)
    assert status == 200, answer
    access = _verify(people, answer["access_token"], API)
    identity = _verify(people, answer["id_token"], SUPERSET)
    assert access["oid"] == identity["oid"] == oid


def test_an_unknown_hint_is_refused_on_entras_own_page(people: str) -> None:
    status, answer = _superset_token(people, "nobody-here@r1.test")
    assert status == 400
    assert "AADSTS50034" in answer["page"]
    words = f"The user account nobody-here@r1.test does not exist in the {TENANT} directory"
    assert words in answer["page"]


def test_r1s_tenant_has_the_four_people_the_dashboards_check_signs_in() -> None:
    """platform-b's check: the administrator, a reader, a builder and a person with no reports
    right, each with the administrator's clearance, unit and codes, holding no role at first
    (Admin › People gives them theirs)."""
    import sys

    gates = Path(__file__).parents[1] / "process/lanes/platform/gates"
    sys.path.insert(0, str(gates))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(gates))
    config = r1_kind.entra_config()
    users = config["users"]
    assert users[0] == config["user"]
    assert [(u["preferred_username"], u["oid"][-2:]) for u in users[1:]] == [
        ("reader@r1.test", "b1"), ("builder@r1.test", "b2"), ("nobody@r1.test", "b3")]
    assert all(u["claims"] == users[0]["claims"] for u in users[1:])
    assert all("roles" not in u["claims"] for u in users)
