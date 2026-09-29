"""Test harness for `deltaClient.test.ts`: runs the *real* `services.api.app`
FastAPI app, over a real socket, against the real ArcadeDB/Valkey/Postgres
`make dev-up` provides.

Why this exists rather than a mock WebSocket server: the constraint this
phase's plan set is "a test that actually drives the client against the
real WebSocket, not a canned fixture of deltas — a mock that only ever
sends well-formed sequential ops won't catch a client that mishandles a
resnapshot". `deltaClient.ts` runs in the
browser; proving it against the real wire contract means a real Python
process serving `/v1/investigations/{id}/stream`, reachable from a Node
`ws` client — not FastAPI's in-process `TestClient`, which never opens an
actual socket.

Reuses the same loopback-JWKS-server-plus-signed-token pattern
`tests/conftest.py` already established for `services/api/auth.py`'s own
tests, standalone rather than as pytest fixtures, since this needs to run
as an independent process a Node test spawns and talks to over stdout —
not inside a pytest session.

Protocol with the caller: print exactly one JSON line to stdout —
`{"port": <int>, "token": "<jwt>"}` — once the server is ready to accept
connections, then block until killed (SIGTERM/SIGINT). `deltaClient.test.ts`
reads that line, runs its assertions, and kills this process afterwards.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

REPO_ROOT = Path(__file__).resolve().parents[3]
# `services.api.app` needs the repo root itself importable (pytest's own
# rootdir-insertion does this implicitly for every test in `tests/` — this
# script runs standalone, so it does the same thing explicitly).
# `pyproject.toml`'s `pythonpath = ["packages"]` is pytest-only config, not
# read by a bare `python` invocation, hence `packages` is added by hand too.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

KID = "glass-test-signing-key"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_jwks_server(tmp_dir: Path) -> tuple[ThreadingHTTPServer, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    (tmp_dir / "jwks.json").write_text(json.dumps({"keys": [jwk]}))

    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[0], server.server_address[1]

    token = jwt.encode(
        {
            "sub": os.environ.get("GLASS_TEST_PRINCIPAL_SUB", "glass-test-analyst"),
            "clearance": os.environ.get("GLASS_TEST_PRINCIPAL_CLEARANCE", "OFFICIAL"),
            "org_unit": os.environ.get("GLASS_TEST_PRINCIPAL_ORG_UNIT", "unit-1"),
            "receivable_handling_codes": [],
            "roles": ["analyst"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": KID},
    )
    return server, f"http://{host}:{port}/jwks.json", token  # type: ignore[return-value]


def main() -> None:
    with TemporaryDirectory() as tmp:
        jwks_server, jwks_url, token = _start_jwks_server(Path(tmp))
        os.environ.setdefault("OIDC_JWKS_URL", jwks_url)

        # Same defaults `make dev-up` stands the stack up on
        # (`services/api/config.py`) — nothing to override when the
        # caller's shell already has the compose stack running on its
        # standard ports.
        #
        # The resnapshot-on-gap case needs the delta stream to have
        # *actually* trimmed something. The real `DELTA_STREAM_MAXLEN`
        # (2000, approximate) would need thousands of real seed calls to
        # exercise honestly — Valkey's approximate `MAXLEN ~` trimming
        # only drops whole internal radix-tree nodes, so a small cap alone
        # does not make it trim promptly. `deltaClient.integration.test.ts`
        # instead issues a real, exact `XTRIM ... MAXLEN 0` directly
        # against Valkey once a couple of real deltas exist — genuinely
        # empties the stream, which is the same `deltas_after` "nothing
        # retained" branch a long-lived investigation's real trimming
        # would eventually hit, without waiting for it.

        port = _free_port()
        print(json.dumps({"port": port, "token": token}), flush=True)

        try:
            uvicorn.run(
                "services.api.app:app",
                host="127.0.0.1",
                port=port,
                log_level="warning",
            )
        finally:
            jwks_server.shutdown()


if __name__ == "__main__":
    main()
