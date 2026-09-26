"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 5 — amendment 22 / `05_DEPLOYMENT.md` §2.5's
third constraint: "/admin is served in console mode only (setup mode returns 404 for /admin;
console mode returns 404 for the setup routes)." `harness/webapp.py`'s own docstring has the full
reasoning for why this is a `mode` `create_app` takes, checked by a middleware ahead of
`require_admin_role`, rather than a flag toggled at runtime — and for why the docker-socket/
read-only-root half of the same constraint is a `harness/Dockerfile` concern this module cannot
express (that half is `test_harness_image.py`'s own scope, needing a real container)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness.webapp import create_app


def _client(tmp_path: Path, *, mode: str) -> TestClient:
    app = create_app(config_path=tmp_path / "osprey.yaml", mode=mode)
    return TestClient(app, client=("127.0.0.1", 51000))


def test_setup_mode_404s_admin_even_with_no_auth_attempted_at_all(tmp_path: Path) -> None:
    """The blunter, deliberate refusal: unlike `require_admin_role`'s own "no JWKS configured yet"
    incidental 404, this one holds even once Launch has configured `OIDC_JWKS_URL` — the route
    itself does not exist in this mode, not merely "no token would currently satisfy it"."""
    response = _client(tmp_path, mode="setup").get("/admin")
    assert response.status_code == 404


def test_setup_mode_404s_admin_even_carrying_a_real_valid_admin_token(
    tmp_path: Path, jwks_url: str, keypair: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    private_key, _ = keypair
    token = sign_token(private_key, default_claims(roles=["osprey-admin"]))
    response = _client(tmp_path, mode="setup").get(
        "/admin", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


def test_console_mode_serves_admin_to_a_real_valid_admin_token(
    tmp_path: Path, jwks_url: str, keypair: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    private_key, _ = keypair
    token = sign_token(private_key, default_claims(roles=["osprey-admin"]))
    response = _client(tmp_path, mode="console").get(
        "/admin", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200


def test_console_mode_404s_every_setup_route() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        client = _client(Path(d), mode="console")
        for path, method in [
            ("/api/config", "get"),
            ("/api/profile-options/local-lite", "get"),
            ("/api/real-data-exceptions", "get"),
            ("/api/geospatial/register-provider", "post"),
            ("/api/preflight/stream", "get"),
            ("/api/artefacts/generate", "post"),
            ("/api/launch/target", "get"),
        ]:
            response = getattr(client, method)(path)
            assert response.status_code == 404, f"{method.upper()} {path}: {response.status_code}"


def test_setup_mode_serves_the_setup_routes_normally() -> None:
    """The other half of the same boundary — setup mode is not merely "not console", it is
    genuinely unchanged from every prior round's own behaviour."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        client = _client(Path(d), mode="setup")
        response = client.get("/api/config")
        assert response.status_code == 200


def test_an_invalid_mode_is_rejected_rather_than_silently_defaulting() -> None:
    with pytest.raises(ValueError, match="mode"):
        create_app(config_path=Path("/nonexistent/osprey.yaml"), mode="not-a-real-mode")
