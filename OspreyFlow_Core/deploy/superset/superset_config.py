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


class OspreySecurityManager(SupersetSecurityManager):
    """Reads who signed in from the access token the provider returned over the back channel —
    never from anything the browser sent — including OspreyFlow's `roles` claim."""

    def oauth_user_info(self, provider, response=None):  # type: ignore[no-untyped-def]
        token = (response or {}).get("access_token", "")
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
