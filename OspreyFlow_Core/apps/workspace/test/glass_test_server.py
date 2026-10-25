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

**The Vault side door (ADR-124 U7).** `/seed` stores only what the Vault returns for the id, so a
test that seeds a node must first have it in ArcadeDB, in a dataset the case reads. A second small
HTTP server on `vault_port` does that: `POST /nodes` with `{"names": [...], "datasets": [...]}`
writes one `Person` per name through the same adapter, schema and database the app uses, and
answers `{"ids": {"<name>": "<node id>"}}`. The ids are made unique per call, so a re-run, or
another test, never meets a node already there. It is a test harness, not a route of the product.

Protocol with the caller: print exactly one JSON line to stdout —
`{"port": <int>, "token": "<jwt>", "vault_port": <int>}` — once the server is ready to accept
connections, then block until killed (SIGTERM/SIGINT). `deltaClient.test.ts`
reads that line, runs its assertions, and kills this process afterwards.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
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


async def _write_nodes(names: list[str], datasets: list[str]) -> dict[str, str]:
    """One OFFICIAL `Person` in the Vault for each name, in `datasets`; the id each got."""
    from services.api.app import app

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme
    from schemas.domain import Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

    ids = {name: f"{name}-{uuid.uuid4().hex[:8]}" for name in names}
    now = datetime.now(UTC)
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        # The schema the app itself applied at start-up: applying it again changes nothing.
        await adapter.apply_schema(app.state.ontology)
        writes = [
            NodeWrite(
                id=node_id,
                type="Person",
                properties={"family_name": name},
                provenance=Provenance(
                    state=ProvenanceState.ASSERTED,
                    sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
                    first_seen=now,
                ),
                handling=Handling(
                    classification="OFFICIAL",
                    handling_code="P",
                    originator="unit-1",
                    owning_unit="unit-1",
                ),
                created_by="glass-test-harness",
                created_at=now,
                datasets=datasets,
            )
            for name, node_id in ids.items()
        ]
        tx = await adapter.begin_transaction()
        written = await adapter.upsert_nodes(writes, tx)
        await adapter.commit_transaction(tx)
        return dict(zip(ids, written, strict=True))
    finally:
        await client.aclose()


class _VaultHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            ids = asyncio.run(_write_nodes(list(body["names"]), list(body["datasets"])))
            payload, status = json.dumps({"ids": ids}).encode(), 200
        except Exception as error:  # noqa: BLE001 - reported to the test, which fails on it
            payload, status = json.dumps({"error": repr(error)}).encode(), 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return None


def _start_vault_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VaultHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


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
        vault_server = _start_vault_server()
        print(
            json.dumps(
                {"port": port, "token": token, "vault_port": vault_server.server_address[1]}
            ),
            flush=True,
        )

        try:
            uvicorn.run(
                "services.api.app:app",
                host="127.0.0.1",
                port=port,
                log_level="warning",
            )
        finally:
            jwks_server.shutdown()
            vault_server.shutdown()


if __name__ == "__main__":
    main()
