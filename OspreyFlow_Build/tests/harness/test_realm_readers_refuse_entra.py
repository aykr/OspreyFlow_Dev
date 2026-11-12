"""The readers of `roles` outside `principal_auth` (`06_DECISIONS.md` ADR-148 Amendment 8; Amendment
6's carried list): each is brought under the rule or shown not rendered on the cloud-platform
profile.

- `harness/webapp_auth.py`'s `require_admin_role` (the set-up console's `/admin`): an Entra ID token
  (one carrying `tid`) is refused (404, as every refusal there), whatever app role it carries. The
  console is the Keycloak realm's and is no workload of the cloud-platform render.
- `harness/oidc.py`'s `verify_id_token` (the launcher's and the Admin console's sign-in): an Entra
  ID token is refused (`entra_token`).
- `deploy/superset/superset_config.py`: on Entra ID sign-in (`SUPERSET_SIGN_IN=entra`, rendered on
  the cloud-platform profile) no token role is read; everyone is Gamma until Superset's own step.

Each refusal's control is the same token without `tid` (or Superset on Keycloak), admitted as
before. Synthetic values only (rule 9).
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from harness.oidc import SignInRefused
from harness.webapp import create_app

from tests.conftest import default_claims, sign_token
from tests.harness.test_oidc import _finish, idp  # noqa: F401 (the fixture)

TENANT = "00000000-1111-4222-8333-444444444444"
CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"


# --- the set-up console's /admin ---


def _console(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(config_path=tmp_path / "osprey.yaml", mode="console"),
        client=("127.0.0.1", 51000),
    )


@pytest.mark.parametrize(("tid", "status"), [(TENANT, 404), (None, 200)], ids=["entra", "control"])
def test_the_consoles_admin_refuses_an_entra_token_with_the_admin_role(
    tmp_path, jwks_url, keypair, monkeypatch, tid, status
) -> None:
    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    claims = default_claims(roles=["osprey-admin"])
    if tid:
        claims["tid"] = tid
    token = sign_token(keypair[0], claims)
    response = _console(tmp_path).get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status


# --- the launcher's and the Admin console's sign-in ---


def test_the_realms_sign_in_refuses_an_entra_id_token(idp) -> None:  # noqa: F811
    idp.claim_overrides = {"tid": TENANT, "roles": ["osprey-admin"]}
    with pytest.raises(SignInRefused) as refused:
        _finish(idp)
    assert refused.value.reason == "entra_token"


def test_the_realms_sign_in_still_admits_its_own_token(idp) -> None:  # noqa: F811
    idp.claim_overrides = {"roles": ["osprey-admin"]}
    assert _finish(idp).roles == ("osprey-admin",)


# --- Superset ---


def _superset(monkeypatch, sign_in: str | None):  # type: ignore[no-untyped-def]
    """`superset_config` loaded as Superset loads it, its two framework imports stood in for."""
    manager = types.ModuleType("flask_appbuilder.security.manager")
    manager.AUTH_OAUTH = 4  # type: ignore[attr-defined]
    security = types.ModuleType("superset.security")
    security.SupersetSecurityManager = object  # type: ignore[attr-defined]
    for name, module in {
        "flask_appbuilder": types.ModuleType("flask_appbuilder"),
        "flask_appbuilder.security": types.ModuleType("flask_appbuilder.security"),
        "flask_appbuilder.security.manager": manager,
        "superset": types.ModuleType("superset"),
        "superset.security": security,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name, value in {
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "SUPERSET_SECRET_KEY": "k",
        "SUPERSET_OIDC_CLIENT_SECRET": "s",
        "SUPERSET_GUEST_TOKEN_SECRET": "g",
    }.items():
        monkeypatch.setenv(name, value)
    if sign_in is None:
        monkeypatch.delenv("SUPERSET_SIGN_IN", raising=False)
    else:
        monkeypatch.setenv("SUPERSET_SIGN_IN", sign_in)
    spec = importlib.util.spec_from_file_location(
        "superset_config_under_test", CORE / "deploy/superset/superset_config.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _access_token(claims: dict[str, object]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{body}.sig"


@pytest.mark.parametrize(
    ("sign_in", "roles"), [("entra", []), (None, ["osprey-admin"])], ids=["entra", "keycloak"]
)
def test_superset_reads_no_token_role_on_entra(monkeypatch, sign_in, roles) -> None:
    config = _superset(monkeypatch, sign_in)
    token = _access_token({"preferred_username": "ana", "roles": ["osprey-admin"], "tid": TENANT})
    info = config.OspreySecurityManager.oauth_user_info(None, "keycloak", {"access_token": token})
    assert info["role_keys"] == roles
    # Gamma for everyone the mapping names nothing for (Flask-AppBuilder's registration role).
    assert config.AUTH_USER_REGISTRATION_ROLE == "Gamma"
