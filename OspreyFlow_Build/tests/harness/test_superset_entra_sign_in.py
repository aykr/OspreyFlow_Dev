"""Superset signs people in through Entra ID (`06_DECISIONS.md` ADR-148 Amendment 9).

`deploy/superset/superset_config.py`, loaded as Superset loads it, with Superset and Flask-AppBuilder
stubbed (neither is installed here; the R1 run on kind is the live proof):

- the OAuth provider is the client's own tenant's v2.0 endpoints, asking for the API's delegated scope;
  no Keycloak address and no multi-tenant endpoint;
- who signed in is the Conduit's own resolution of the person (`GET /v1/me`, `/v1/me/rights`) with the
  delegated token Entra returned, never a token claim: the username is the principal's id (the object
  id), `administer_system` is Admin, `read_reports` Gamma, neither no account;
- every refusal or failure of the Conduit refuses the sign-in (fails closed).

The Conduit here is a stand-in answering with the real response models (`schemas.rights`) and
refusing as the real one does: 401 for a token it cannot resolve, 403 for a route the principal may
not use, and nothing at all when it is down (rule 15: what the real one refuses, the fake refuses).
Synthetic values only (rule 9).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import types
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from schemas.rights import MeResponse, Right, RightsResponse

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
TENANT = "00000000-1111-4222-8333-444444444444"
SUPERSET_APP = "11111111-2222-4333-8444-555555555555"
API_SCOPE = "api://22222222-3333-4444-8555-666666666666/access_as_user"
ANA = "aaaaaaaa-0000-4000-8000-000000000001"


class Conduit(ThreadingHTTPServer):
    """`GET /v1/me` and `/v1/me/rights` for the tokens it knows: token -> (me, rights)."""

    people: dict[str, tuple[MeResponse, RightsResponse]]
    refuse_rights: bool
    asked: list[tuple[str, str]]


@pytest.fixture
def conduit() -> Iterator[Conduit]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            server: Conduit = self.server  # type: ignore[assignment]
            token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
            server.asked.append((self.path, token))
            person = server.people.get(token)
            if person is None:
                return self._send(401, {"detail": "the token could not be resolved"})
            if self.path == "/v1/me":
                return self._send(200, person[0].model_dump(mode="json"))
            if self.path == "/v1/me/rights" and not server.refuse_rights:
                return self._send(200, person[1].model_dump(mode="json"))
            return self._send(403, {"detail": "not for this principal"})

        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args: object) -> None:
            pass

    server = Conduit(("127.0.0.1", 0), Handler)
    server.people, server.refuse_rights, server.asked = {}, False, []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()


def _person(conduit: Conduit, token: str, *rights: Right, oid: str = ANA) -> None:
    me = MeResponse(id=oid, clearance="OFFICIAL", org_unit="unit-a", roles=["analyst"],
                    receivable_handling_codes=["P"])  # fmt: skip
    conduit.people[token] = (me, RightsResponse(rights=list(rights)))


def _superset(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> Any:
    manager = types.ModuleType("flask_appbuilder.security.manager")
    manager.AUTH_OAUTH = 4  # type: ignore[attr-defined]
    security = types.ModuleType("superset.security")
    security.SupersetSecurityManager = type("SupersetSecurityManager", (), {})  # type: ignore[attr-defined]
    for name, module in {
        "flask_appbuilder": types.ModuleType("flask_appbuilder"),
        "flask_appbuilder.security": types.ModuleType("flask_appbuilder.security"),
        "flask_appbuilder.security.manager": manager,
        "superset": types.ModuleType("superset"),
        "superset.security": security,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    base = {"POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p", "SUPERSET_SECRET_KEY": "k",
            "SUPERSET_OIDC_CLIENT_SECRET": "s", "SUPERSET_GUEST_TOKEN_SECRET": "g"}  # fmt: skip
    for name in ("SUPERSET_SIGN_IN", "SUPERSET_ENTRA_TENANT", "SUPERSET_OIDC_CLIENT_ID",
                 "SUPERSET_ENTRA_API_SCOPE", "SUPERSET_CONDUIT_URL", "SUPERSET_ENTRA_AUTHORITY",
                 "SUPERSET_IDP_INTERNAL", "SUPERSET_IDP_PUBLIC", "SUPERSET_IDP_ISSUER",
                 "SUPERSET_RATELIMIT_STORAGE"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    for name, value in {**base, **env}.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location(
        "superset_config_under_test", CORE / "deploy/superset/superset_config.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entra(monkeypatch: pytest.MonkeyPatch, conduit: Conduit | None = None) -> Any:
    return _superset(monkeypatch, {
        "SUPERSET_SIGN_IN": "entra",
        "SUPERSET_ENTRA_TENANT": TENANT,
        "SUPERSET_OIDC_CLIENT_ID": SUPERSET_APP,
        "SUPERSET_ENTRA_API_SCOPE": API_SCOPE,
        "SUPERSET_CONDUIT_URL": f"http://127.0.0.1:{conduit.server_address[1]}" if conduit else "http://127.0.0.1:9",
    })  # fmt: skip


def _sign_in(config: Any, token: str, userinfo: dict[str, Any] | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {"access_token": token}
    if userinfo is not None:
        response["userinfo"] = userinfo
    return config.OspreySecurityManager().oauth_user_info("entra", response)


# --- the provider ---


def test_the_provider_is_the_tenant_s_own_v2_endpoints_asking_for_the_api_s_scope(monkeypatch) -> None:
    config = _entra(monkeypatch)
    [provider] = config.OAUTH_PROVIDERS
    app = provider["remote_app"]
    tenant = f"https://login.microsoftonline.com/{TENANT}"
    assert provider["name"] == "entra"
    assert app["client_id"] == SUPERSET_APP
    assert app["authorize_url"] == f"{tenant}/oauth2/v2.0/authorize"
    assert app["access_token_url"] == f"{tenant}/oauth2/v2.0/token"
    assert app["jwks_uri"] == f"{tenant}/discovery/v2.0/keys"
    assert app["issuer"] == f"{tenant}/v2.0"
    assert app["client_kwargs"]["scope"].split() == ["openid", "profile", API_SCOPE]
    text = json.dumps(config.OAUTH_PROVIDERS)
    assert "keycloak" not in text and "/common/" not in text and "/organizations/" not in text


@pytest.mark.parametrize("missing", ["SUPERSET_ENTRA_TENANT", "SUPERSET_OIDC_CLIENT_ID", "SUPERSET_ENTRA_API_SCOPE"])
def test_an_entra_setting_left_out_stops_superset_starting(monkeypatch, missing: str) -> None:
    env = {"SUPERSET_SIGN_IN": "entra", "SUPERSET_ENTRA_TENANT": TENANT,
           "SUPERSET_OIDC_CLIENT_ID": SUPERSET_APP, "SUPERSET_ENTRA_API_SCOPE": API_SCOPE}  # fmt: skip
    del env[missing]
    with pytest.raises(KeyError, match=missing):
        _superset(monkeypatch, env)


def test_keycloak_s_provider_is_as_before_without_entra(monkeypatch) -> None:
    config = _superset(monkeypatch, {})
    [provider] = config.OAUTH_PROVIDERS
    assert provider["name"] == "keycloak"
    assert provider["remote_app"]["client_id"] == "osprey-superset"


# --- who signed in: the Conduit's principal ---


@pytest.mark.parametrize(
    ("rights", "role_keys"),
    [
        ((Right.ADMINISTER_SYSTEM, Right.READ_REPORTS), ["osprey-admin"]),
        ((Right.ADMINISTER_SYSTEM,), ["osprey-admin"]),
        ((Right.READ_REPORTS, Right.READ_REPORT_FEED), ["reports_viewer"]),
        ((Right.MANAGE_DASHBOARDS, Right.READ_REPORTS), ["dashboard_builder"]),
        ((Right.MANAGE_DASHBOARDS,), ["dashboard_builder"]),
    ],
    ids=["admin", "admin-without-reports", "reports", "builder", "builder-without-reports"],
)
def test_the_role_is_the_conduit_s_rights_and_the_account_its_principal(
    monkeypatch, conduit: Conduit, rights: tuple[Right, ...], role_keys: list[str]
) -> None:
    _person(conduit, "t-ana", *rights)
    info = _sign_in(_entra(monkeypatch, conduit), "t-ana", {"name": "Ana", "oid": "someone-else"})
    assert info["role_keys"] == role_keys
    assert info["username"] == ANA  # the Conduit's id, never the ID token's
    assert info["first_name"] == "Ana"
    assert [path for path, _ in conduit.asked] == ["/v1/me", "/v1/me/rights"]
    assert {token for _, token in conduit.asked} == {"t-ana"}


def test_a_token_s_own_roles_are_never_read(monkeypatch, conduit: Conduit) -> None:
    """An Entra token's `roles` are app roles (Amendment 8): an access token claiming osprey-admin
    for a person whose rights are reports only is Gamma."""
    import base64

    body = base64.urlsafe_b64encode(json.dumps({"roles": ["osprey-admin"], "tid": TENANT}).encode())
    token = f"e30.{body.decode().rstrip('=')}.sig"
    _person(conduit, token, Right.READ_REPORTS)
    assert _sign_in(_entra(monkeypatch, conduit), token)["role_keys"] == ["reports_viewer"]


def test_neither_right_is_no_account(monkeypatch, conduit: Conduit) -> None:
    _person(conduit, "t-bo", Right.INVESTIGATE, Right.READ_REPORT_FEED)
    config = _entra(monkeypatch, conduit)
    with pytest.raises(config.NotForReports, match="no reports account"):
        _sign_in(config, "t-bo")


@pytest.mark.parametrize("case", ["unresolved-token", "rights-refused", "conduit-down", "no-token"])
def test_any_refusal_or_failure_of_the_conduit_refuses_the_sign_in(
    monkeypatch, conduit: Conduit, case: str
) -> None:
    """Fails closed: never an account on a guess, never Gamma by default."""
    _person(conduit, "t-ana", Right.ADMINISTER_SYSTEM)
    config = _entra(monkeypatch, None if case == "conduit-down" else conduit)
    if case == "rights-refused":
        conduit.refuse_rights = True
    token = {"unresolved-token": "t-unknown", "no-token": ""}.get(case, "t-ana")
    with pytest.raises(Exception) as raised:
        _sign_in(config, token)
    assert not isinstance(raised.value, (AssertionError, KeyError))


def test_keycloak_s_sign_in_still_reads_the_realm_s_roles_claim(monkeypatch) -> None:
    import base64

    body = base64.urlsafe_b64encode(json.dumps({"preferred_username": "ana", "roles": ["osprey-admin"]}).encode())
    token = f"e30.{body.decode().rstrip('=')}.sig"
    info = _superset(monkeypatch, {}).OspreySecurityManager().oauth_user_info("keycloak", {"access_token": token})
    assert info["role_keys"] == ["osprey-admin"] and info["username"] == "ana"


# --- its rate limits in the managed cache (ADR-148 Amendment 11) ---


def test_the_rate_limits_go_to_the_managed_cache_over_tls_with_its_password(monkeypatch) -> None:
    """The cloud-platform render gives no SUPERSET_RATELIMIT_STORAGE (the cluster's names a Valkey
    the profile does not run); the cache's secret gives VALKEY_*, and VALKEY_TLS is the ConfigMap's."""
    config = _superset(monkeypatch, {"VALKEY_HOST": "cache.example.internal", "VALKEY_PORT": "6380",
                                     "VALKEY_PASSWORD": "p@ss/word", "VALKEY_TLS": "true"})  # fmt: skip
    assert config.RATELIMIT_STORAGE_URI == "rediss://:p%40ss%2Fword@cache.example.internal:6380/5"


def test_small_s_rate_limit_address_is_as_before(monkeypatch) -> None:
    for name in ("VALKEY_HOST", "VALKEY_PORT", "VALKEY_PASSWORD", "VALKEY_TLS"):
        monkeypatch.delenv(name, raising=False)
    assert _superset(monkeypatch, {}).RATELIMIT_STORAGE_URI == "redis://valkey:6379/5"
    named = _superset(monkeypatch, {"SUPERSET_RATELIMIT_STORAGE": "redis://valkey:6379/5", "VALKEY_HOST": "x"})
    assert named.RATELIMIT_STORAGE_URI == "redis://valkey:6379/5"


def test_a_builder_is_superset_s_alpha_and_a_reports_viewer_stays_read_only(monkeypatch) -> None:
    """The owner's ruling of 13 November 2026 (Q2): a holder of `manage_dashboards` builds (Alpha:
    charts and dashboards on the data sources it may read, the mart alone); a Reports Viewer is Gamma,
    read-only; an administrator is Admin. Superset's own roles grant the rest, which the v0.5.2 R1 run's
    dashboards check measures (a builder saves a chart, a Reports Viewer is refused)."""
    mapping = _entra(monkeypatch).AUTH_ROLES_MAPPING
    assert mapping["dashboard_builder"] == ["Alpha"]
    assert mapping["reports_viewer"] == ["Gamma"] and mapping["osprey-admin"] == ["Admin"]
    assert not {"Alpha", "Admin"} & {r for k, v in mapping.items() if k != "osprey-admin" and k != "dashboard_builder" for r in v}

