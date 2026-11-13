"""Superset for OspreyFlow (`06_DECISIONS.md` ADR-111 Amendment 2): every value from the
environment the deployment renders — nothing secret in this file.

**Single sign-on.** People sign in through the deployment's identity provider (`osprey-superset`,
a confidential client). Their roles come from the access token the provider returns to Superset over
the deployment's own network — `osprey-admin` is Superset's Admin, every other OspreyFlow role its
read-only Gamma — synchronised at each sign-in. The browser is sent to the provider's public
address; Superset's own calls use its internal one, including fetching the keys its id_token is
verified against.

**It reads only the mart,** through `REPORT_MART_READER`, a login that may select from
`osprey_reports` and nothing else (registered by `osprey_entrypoint.py`).
"""

import base64
import json
import os
import urllib.request
from urllib.parse import quote

from flask_appbuilder.security.manager import AUTH_OAUTH
from superset.security import SupersetSecurityManager

# Escaped: a password a cloud's secret store made may hold any character (`05_DEPLOYMENT.md` §3a).
_user = quote(os.environ["POSTGRES_USER"], safe="")
_password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
_pg = (
    f"{_user}:{_password}"
    f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:{os.environ.get('POSTGRES_PORT', '5432')}"
)
_tls = f"?sslmode={os.environ['POSTGRES_SSLMODE']}" if os.environ.get("POSTGRES_SSLMODE") else ""
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
_metadata_db = os.environ.get("SUPERSET_METADATA_DB", "superset")
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{_pg}/{_metadata_db}{_tls}"

AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Gamma"
AUTH_ROLES_SYNC_AT_LOGIN = True
AUTH_ROLES_MAPPING = {
    "osprey-admin": ["Admin"],
    "reports_viewer": ["Gamma"],
    "analyst": ["Gamma"],
    "data_engineer": ["Gamma"],
}

#: Rendered on the cloud-platform profile, whose people sign in with Entra ID (ADR-148 decision 9).
_ENTRA = os.environ.get("SUPERSET_SIGN_IN", "").lower() == "entra"

if not _ENTRA:
    _internal = os.environ.get("SUPERSET_IDP_INTERNAL", "http://keycloak:8080/realms/osprey")
    _public = os.environ.get("SUPERSET_IDP_PUBLIC", "http://id.ospreyflow.localhost/realms/osprey")
    OAUTH_PROVIDERS = [
        {
            "name": "keycloak",
            "icon": "fa-key",
            "token_key": "access_token",
            "remote_app": {
                "client_id": os.environ.get("SUPERSET_OIDC_CLIENT_ID", "osprey-superset"),
                "client_secret": os.environ["SUPERSET_OIDC_CLIENT_SECRET"],
                "api_base_url": f"{_internal}/protocol/openid-connect/",
                "access_token_url": f"{_internal}/protocol/openid-connect/token",
                "authorize_url": f"{_public}/protocol/openid-connect/auth",
                "client_kwargs": {"scope": "openid profile"},
                # The id_token is verified: signature against the realm's keys, fetched over the
                # internal network; audience, nonce and issuer. A browser sign-in's id_token carries
                # the public issuer — the address the person signed in at — even though Superset
                # fetches it internally (measured: the internal issuer was refused, `invalid_claim`);
                # `SUPERSET_IDP_ISSUER` names another for a realm with a fixed hostname. Without
                # `jwks_uri` every sign-in was refused ("Missing jwks_uri in metadata", found live 11
                # October 2026).
                "jwks_uri": f"{_internal}/protocol/openid-connect/certs",
                "issuer": os.environ.get("SUPERSET_IDP_ISSUER", _public),
            },
        }
    ]

else:
    # ADR-148 Amendment 9: Superset is its own app registration in the client's tenant, and asks Entra
    # for an ID token (its own sign-in) and a delegated token for OspreyFlow's API scope, which it
    # spends on the Conduit's `GET /v1/me` and `/v1/me/rights` alone (the Conduit admits Superset's
    # client there and nowhere else). Every address is the tenant's own: no `common` or
    # `organizations` endpoint, so a person of another tenant is refused by Entra before Superset.
    _tenant = os.environ["SUPERSET_ENTRA_TENANT"]
    _authority = os.environ.get("SUPERSET_ENTRA_AUTHORITY", "https://login.microsoftonline.com")
    _entra = f"{_authority.rstrip('/')}/{_tenant}"
    OAUTH_PROVIDERS = [
        {
            "name": "entra",
            "icon": "fa-windows",
            "token_key": "access_token",
            "remote_app": {
                "client_id": os.environ["SUPERSET_OIDC_CLIENT_ID"],
                "client_secret": os.environ["SUPERSET_OIDC_CLIENT_SECRET"],
                "api_base_url": f"{_entra}/oauth2/v2.0/",
                "access_token_url": f"{_entra}/oauth2/v2.0/token",
                "authorize_url": f"{_entra}/oauth2/v2.0/authorize",
                "client_kwargs": {"scope": f"openid profile {os.environ['SUPERSET_ENTRA_API_SCOPE']}"},
                # The ID token is Superset's own (its audience Superset's registration), verified
                # against the tenant's keys and its v2.0 issuer, whatever the API's token version.
                "jwks_uri": f"{_entra}/discovery/v2.0/keys",
                "issuer": f"https://login.microsoftonline.com/{_tenant}/v2.0",
            },
        }
    ]

#: Where Superset asks the Conduit who signed in (inside the deployment's network).
_CONDUIT = os.environ.get("SUPERSET_CONDUIT_URL", "http://api:8000").rstrip("/")


class NotForReports(Exception):
    """The person holds neither `administer_system` nor `read_reports`: no Superset account. Raised
    from `oauth_user_info`, which Flask-AppBuilder answers as a refused sign-in."""


def _conduit(path: str, access_token: str) -> dict:  # type: ignore[type-arg]
    """One read of the person's own principal, as the Conduit resolved it. Any refusal or failure
    is raised, so the sign-in is refused: never an account on a guess (fails closed)."""
    request = urllib.request.Request(
        f"{_CONDUIT}{path}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as answer:  # noqa: S310 - the deployment's Conduit
        return json.load(answer)


class OspreySecurityManager(SupersetSecurityManager):
    """Reads who signed in from what came back over the back channel — never from anything the
    browser sent. Keycloak: OspreyFlow's `roles` claim of the access token. Entra ID (ADR-148
    Amendment 9): the Conduit's own resolution of the person (`GET /v1/me`, `/v1/me/rights`), since
    an Entra token's `roles` are app roles, never OspreyFlow's."""

    def oauth_user_info(self, provider, response=None):  # type: ignore[no-untyped-def]
        token = (response or {}).get("access_token", "")
        if _ENTRA:
            return _entra_user_info(response or {}, token)
        payload = token.split(".")[1] if token.count(".") == 2 else ""
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded)) if payload else {}
        return {
            "username": claims.get("preferred_username", ""),
            "first_name": claims.get("given_name", ""),
            "last_name": claims.get("family_name", ""),
            "email": claims.get("email")
            or f"{claims.get('preferred_username', 'user')}@ospreyflow.invalid",
            "role_keys": claims.get("roles", []),
        }


def _entra_user_info(response: dict, access_token: str) -> dict:  # type: ignore[type-arg]
    """The account is the Conduit's principal: its id (the Entra object id) is the username, and its
    rights decide the role, re-read at every sign-in (`AUTH_ROLES_SYNC_AT_LOGIN`): `administer_system`
    is Superset's Admin, `read_reports` its read-only Gamma, neither no account at all. Only the
    displayed name comes from the ID token (verified by Superset's OAuth client against the tenant)."""
    if not access_token:
        raise NotForReports("no delegated token came back from Entra ID")
    me = _conduit("/v1/me", access_token)
    rights = set(_conduit("/v1/me/rights", access_token).get("rights", []))
    if "administer_system" in rights:
        role_keys = ["osprey-admin"]
    elif "read_reports" in rights:
        role_keys = ["reports_viewer"]
    else:
        raise NotForReports("neither administer_system nor read_reports: no reports account")
    person = str(me["id"])
    shown = response.get("userinfo") or {}
    return {
        "username": person,
        "first_name": str(shown.get("given_name") or shown.get("name") or ""),
        "last_name": str(shown.get("family_name") or ""),
        "email": f"{person}@ospreyflow.invalid",
        "role_keys": role_keys,
    }


CUSTOM_SECURITY_MANAGER = OspreySecurityManager

# --- OspreyFlow's look (ADR-111 Amendment 4): Superset 6's light and dark themes, generated from
# the Glass's design tokens (`scripts/superset_theme.py` -> `osprey_theme.json`, copied in beside
# this file) — surfaces, text, the one accent (brass), the type families and each theme's nine chart
# channels. Nothing here names a colour of its own. The Glass chooses the mode of a board it frames
# (the embedded SDK's `themeMode`); Superset's own pages follow the browser's preference. Themes are
# not edited inside Superset: one changed there would drift from the tokens unseen. The mark and
# favicon are the OspreyFlow mark in the light theme's ink, beside the short-form wordmark. ---
with open(os.path.join(os.path.dirname(__file__), "osprey_theme.json"), encoding="utf-8") as _file:
    _themes = json.load(_file)
THEME_DEFAULT = _themes["default"]
THEME_DARK = _themes["dark"]
ENABLE_UI_THEME_ADMINISTRATION = False
APP_NAME = "OspreyFlow Reports"
APP_ICON = "/static/assets/images/osprey-mark.svg"
LOGO_TOOLTIP = "OspreyFlow"
LOGO_RIGHT_TEXT = "Osprey"
FAVICONS = [{"href": "/static/assets/images/osprey-favicon.svg", "type": "image/svg+xml"}]
EXTRA_CATEGORICAL_COLOR_SCHEMES = [
    {
        "id": "ospreyflow",
        "label": "OspreyFlow",
        "description": "The OspreyFlow data palette: nine channels, never brass",
        "isDefault": True,
        "colors": _themes["categorical"]["colors"],
    }
]
EXTRA_SEQUENTIAL_COLOR_SCHEMES = [
    {
        "id": "ospreyflow_sequential",
        "label": "OspreyFlow magnitude",
        "isDiverging": False,
        "isDefault": True,
        "colors": _themes["sequential"]["colors"],
    }
]
FEATURE_FLAGS = {"DASHBOARD_RBAC": True, "EMBEDDED_SUPERSET": True}

# --- Embedded in the Glass (ADR-111 Amendment 3). The Conduit asks for guest tokens as the local
# service user `osprey-embedder` (made by osprey_setup.py); a guest reads only the mart, and its
# token carries a row-level rule naming one dashboard identity. Superset's own content security
# policy is kept as shipped — only the Glass's origin is added as a permitted framer. ---
GUEST_ROLE_NAME = "OspreyEmbedded"
GUEST_TOKEN_JWT_SECRET = os.environ["SUPERSET_GUEST_TOKEN_SECRET"]
GUEST_TOKEN_JWT_EXP_SECONDS = 300
_glass = os.environ.get("SUPERSET_GLASS_ORIGIN", "http://ospreyflow.localhost")
TALISMAN_CONFIG = {
    "content_security_policy": {
        "base-uri": ["'self'"],
        "default-src": ["'self'"],
        "img-src": ["'self'", "blob:", "data:", "https://apachesuperset.gateway.scarf.sh",
                    "https://static.scarf.sh/"],
        "worker-src": ["'self'", "blob:"],
        "connect-src": ["'self'", "https://api.mapbox.com", "https://events.mapbox.com"],
        "object-src": "'none'",
        "style-src": ["'self'", "'unsafe-inline'"],
        "script-src": ["'self'", "'strict-dynamic'"],
        "frame-ancestors": ["'self'", _glass],
    },
    "content_security_policy_nonce_in": ["script-src"],
    "force_https": False,
    "session_cookie_secure": False,
}  # fmt: skip
# Superset's own content security policy stays on (its default); rate limits are counted in the
# deployment's Valkey, so every worker and replica counts together.
# Reached only through the deployment's front proxy (ADR-114 Amendment 4), which is the only thing
# that can send these headers: trust its scheme and host when building sign-in redirects.
ENABLE_PROXY_FIX = True
RATELIMIT_STORAGE_URI = os.environ.get("SUPERSET_RATELIMIT_STORAGE", "redis://valkey:6379/5")
