"""Repo-wide pytest fixtures.

The OIDC fixtures below back every test that needs a real, signed bearer
token against `services/api/auth.py`'s `PrincipalResolver` — an RSA
keypair plus a loopback HTTP server serving the resulting JWKS document.
`PyJWKClient` (the underlying OIDC client) rejects any URI scheme but
`http`/`https`, so this is a real ephemeral HTTP server, not a `file://`
URL — see `services/api/auth.py`'s module docstring for why.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

DEFAULT_KID = "test-signing-key-1"


@pytest.fixture
def keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture
def jwks_dir(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """A loopback HTTP server rooted at `tmp_path`, serving whatever
    `jwks.json` it finds there fresh on every request — a test can
    overwrite the file mid-test (a key-rotation scenario) and the next
    fetch sees the new content, the same as a real JWKS endpoint's
    content changing without the server restarting."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield tmp_path, f"http://{host}:{port}/jwks.json"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def jwks_url(
    jwks_dir: tuple[Path, str], keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> str:
    directory, url = jwks_dir
    _, public_key = keypair
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = DEFAULT_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    (directory / "jwks.json").write_text(json.dumps({"keys": [jwk]}))
    return url


def sign_token(
    private_key: rsa.RSAPrivateKey, claims: dict[str, object], *, kid: str = DEFAULT_KID
) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def default_claims(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sub": "analyst-1",
        "clearance": "OFFICIAL",
        "org_unit": "unit-1",
        "receivable_handling_codes": [],
        "roles": ["analyst"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    base.update(overrides)
    return base
