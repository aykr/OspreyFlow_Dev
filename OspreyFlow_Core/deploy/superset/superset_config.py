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

from flask_appbuilder.security.manager import AUTH_OAUTH
from superset.security import SupersetSecurityManager

_pg = (
    f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:{os.environ.get('POSTGRES_PORT', '5432')}"
)
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = f"postgresql+pg8000://{_pg}/{os.environ.get('SUPERSET_METADATA_DB', 'superset')}"

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
_public = os.environ.get("SUPERSET_IDP_PUBLIC", "http://localhost:8081/realms/osprey")
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
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))) if payload else {}
        return {
            "username": claims.get("preferred_username", ""),
            "first_name": claims.get("given_name", ""),
            "last_name": claims.get("family_name", ""),
            "email": claims.get("email") or f"{claims.get('preferred_username', 'user')}@ospreyflow.invalid",
            "role_keys": claims.get("roles", []),
        }


CUSTOM_SECURITY_MANAGER = OspreySecurityManager
FEATURE_FLAGS = {"DASHBOARD_RBAC": True}
# Superset's own content security policy stays on (its default); rate limits are counted in the
# deployment's Valkey, so every worker and replica counts together.
RATELIMIT_STORAGE_URI = os.environ.get("SUPERSET_RATELIMIT_STORAGE", "redis://valkey:6379/5")
