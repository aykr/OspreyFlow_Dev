"""`06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 22, and `DECISIONS.md` ruling R2: "`/admin`
requires a valid OIDC bearer token carrying the realm role `osprey-admin`... any request without
one receives 404, never 401, so the endpoint's existence cannot be inferred."

**Real requests, a real RSA-signed token and a real, loopback JWKS HTTP server — `tests/
conftest.py`'s own `keypair`/`jwks_url` fixtures, the same ones `services/api/auth.py`'s own tests
use** (`CLAUDE.md` rule 15: "the injected condition must be the real shape"). Nothing here mocks
`require_admin_role` itself or monkeypatches a boolean flag; every case is an actual HTTP request
through `TestClient` against the real dependency, differing only in what the request carries.

**Shown red before this dependency existed, not only asserted green after** — verified directly
while building this file: with `dependencies=[Depends(require_admin_role)]` removed from `/admin`
in `harness/webapp.py`, `test_a_request_with_no_bearer_token_is_refused_as_not_found` fails (the
route answers 200, not 404). Restored, the same test passes. Not re-run as a permanent test here
— that would be a second copy of the same route drifting from the real one — recorded as this
file's own verification instead, the same shape `tests/test_test_file_coverage_check.py` and
others in this session already use for a gate that cannot easily plant its own removal as code.

**`mode="console"`, deliberately, in every case below** (Stage 2 §6 part B, amendment 22's own
third constraint): `/admin` is reachable at all only in console mode — `test_webapp_mode.py` is
where the mode boundary itself is proven (setup mode 404s `/admin` even carrying a perfectly valid
admin token, before `require_admin_role` is ever consulted). This file's own scope stays the role
gate that runs once mode has already admitted the request.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from harness.webapp import create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app(config_path=tmp_path / "osprey.yaml", mode="console")
    return TestClient(app, client=("127.0.0.1", 51000))


def test_a_request_with_no_bearer_token_is_refused_as_not_found(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/admin")
    assert response.status_code == 404


def test_a_malformed_authorization_header_is_refused_as_not_found(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/admin", headers={"Authorization": "not-a-bearer-token"})
    assert response.status_code == 404


def test_a_well_formed_but_unsigned_garbage_token_is_refused_as_not_found(
    tmp_path: Path, jwks_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    response = _client(tmp_path).get("/admin", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 404


def test_a_real_token_without_the_admin_role_is_refused_as_not_found(
    tmp_path: Path, jwks_url: str, keypair: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    private_key, _ = keypair
    token = sign_token(private_key, default_claims(roles=["analyst"]))
    response = _client(tmp_path).get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_an_expired_real_token_with_the_admin_role_is_refused_as_not_found(
    tmp_path: Path, jwks_url: str, keypair: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    private_key, _ = keypair
    now = int(time.time())
    token = sign_token(
        private_key,
        default_claims(roles=["osprey-admin"], iat=now - 600, exp=now - 300),
    )
    response = _client(tmp_path).get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_a_real_token_carrying_the_admin_role_is_admitted(
    tmp_path: Path, jwks_url: str, keypair: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    private_key, _ = keypair
    token = sign_token(private_key, default_claims(roles=["osprey-admin"]))
    response = _client(tmp_path).get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "not yet built" in response.json()["status"]


def test_a_token_with_the_wrong_audience_is_refused_as_not_found(
    tmp_path: Path, jwks_url: str, keypair: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: "verified with the same audience check the Conduit uses" — an admin role alone is not
    enough if the token was minted for a different client entirely."""
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    monkeypatch.setenv("OIDC_AUDIENCE", "osprey-conduit")
    private_key, _ = keypair
    token = sign_token(
        private_key, default_claims(roles=["osprey-admin"], aud="some-other-client")
    )
    response = _client(tmp_path).get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_a_token_with_the_right_audience_is_admitted(
    tmp_path: Path, jwks_url: str, keypair: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import default_claims, sign_token

    monkeypatch.setenv("OIDC_JWKS_URL", jwks_url)
    monkeypatch.setenv("OIDC_AUDIENCE", "osprey-conduit")
    private_key, _ = keypair
    token = sign_token(
        private_key, default_claims(roles=["osprey-admin"], aud="osprey-conduit")
    )
    response = _client(tmp_path).get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
