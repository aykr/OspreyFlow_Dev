"""Statelessness — `docs/03_CONDUIT_MIDDLEWARE.md` §1: "Any Conduit
instance can serve any request for any session; kill one mid-investigation
and the analyst notices nothing." `docs/07_BUILD_PLAN.md` Phase 3's exit
criterion asks this to be proven, not assumed.

**Two real `uvicorn` processes**, not two Python objects in one process —
strengthened per the divergence-follow-up review, which correctly named
the earlier version (two `WorkingSetService` instances sharing one
process) as short of "kill a running instance and hit a second one".
Both processes are pointed at the same ArcadeDB/Valkey/Postgres; the first
is sent real HTTP requests, then killed outright (`Popen.kill()`, not a
graceful shutdown — an actual "the instance is gone", not a clean exit
this test could accidentally rely on); the second, with no memory of the
first beyond what the shared stores hold, is sent the rest of the same
scripted session and must continue it seamlessly.

**Each instance gets its own scratch analytics DuckDB path, deliberately
not a shared one.** Confirmed empirically (Phase 5 Checkpoint 2): DuckDB
takes an exclusive file lock, and a second process opening the same file
— even read-only — while the first still holds it fails outright, not
gracefully. That is a real, narrower-than-the-rest-of-the-store limitation
of the native single-file store this checkpoint deliberately chose over
the Parquet-in-object-storage design (`analytics_duckdb/testing.py`'s own
docstring, this phase's plan), not something this test is asserting
around — this test's own scope, per its docstring above, is investigation
continuity through ArcadeDB/Valkey/Postgres, and neither request this
script sends touches an `/v1/analytics/*` route at all.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import websockets.sync.client as ws_client
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.conftest import default_claims, sign_token


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_up(base_url: str, *, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base_url}/docs", timeout=1.0)
            return
        except httpx.HTTPError as exc:  # noqa: PERF203 - polling loop, not a hot path
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"{base_url} never came up") from last_error


class _ConduitInstance:
    """One real `uvicorn services.api.app:app` process on its own port,
    sharing the ambient ArcadeDB/Valkey/Postgres env with the test."""

    def __init__(self, jwks_url: str) -> None:
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        repo_root = Path(__file__).resolve().parents[3]
        # `pytest`'s own `pythonpath = ["packages"]` (pyproject.toml) only
        # affects this process's `sys.path`, not a `subprocess.Popen` —
        # `uvicorn` here needs the same `packages` root on `PYTHONPATH`
        # explicitly, the same way `services/api/Dockerfile` sets it.
        packages_root = repo_root / "packages"
        # Its own scratch analytics path, not the shared default — see this
        # module's own docstring for why two instances cannot share one.
        analytics_db_path = (
            Path(tempfile.mkdtemp(prefix="ospreyflow-analytics-")) / "analytics.duckdb"
        )
        env = {
            **os.environ,
            "OIDC_JWKS_URL": jwks_url,
            "OIDC_ALGORITHMS": "RS256",
            "ARCADEDB_DATABASE": "ospreyflow",
            "PYTHONPATH": f"{repo_root}:{packages_root}:{os.environ.get('PYTHONPATH', '')}",
            "ANALYTICS_DB_PATH": str(analytics_db_path),
        }
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "services.api.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            env=env,
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_until_up(self.base_url)

    def kill(self) -> None:
        """Not `terminate()` — this proves the *second* instance's
        continuity does not depend on the first having shut down
        cleanly, only on the stores it wrote to."""
        self._process.kill()
        self._process.wait(timeout=10)


@pytest.fixture
def two_instances(jwks_url: str) -> Iterator[tuple[_ConduitInstance, _ConduitInstance]]:
    instance_a = _ConduitInstance(jwks_url)
    instance_b = _ConduitInstance(jwks_url)
    try:
        yield instance_a, instance_b
    finally:
        for instance in (instance_a, instance_b):
            if instance._process.poll() is None:
                instance._process.kill()
                instance._process.wait(timeout=10)


def _bearer(private_key: rsa.RSAPrivateKey) -> dict[str, str]:
    token = sign_token(private_key, default_claims())
    return {"Authorization": f"Bearer {token}"}


def test_a_second_process_continues_an_investigation_the_first_was_killed_mid(
    two_instances: tuple[_ConduitInstance, _ConduitInstance],
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
) -> None:
    instance_a, instance_b = two_instances
    private_key, _ = keypair
    headers = _bearer(private_key)

    created = httpx.post(f"{instance_a.base_url}/v1/investigations", headers=headers)
    assert created.status_code == 201, created.text
    investigation_id = created.json()["id"]

    seeded_a = httpx.post(
        f"{instance_a.base_url}/v1/investigations/{investigation_id}/seed",
        headers=headers,
        json={"nodes": [_seed_node("from-a")], "edges": []},
    )
    assert seeded_a.status_code == 200, seeded_a.text
    assert seeded_a.json()["delta"]["seq"] == 1

    # Kill instance A outright, mid-investigation. It is never contacted
    # again by this test.
    instance_a.kill()

    # Instance B — a process that has never seen this investigation
    # before — continues it, using only what ArcadeDB/Valkey/Postgres
    # hold.
    fetched = httpx.get(
        f"{instance_b.base_url}/v1/investigations/{investigation_id}", headers=headers
    )
    assert fetched.status_code == 200, fetched.text

    seeded_b = httpx.post(
        f"{instance_b.base_url}/v1/investigations/{investigation_id}/seed",
        headers=headers,
        json={"nodes": [_seed_node("from-b")], "edges": []},
    )
    assert seeded_b.status_code == 200, seeded_b.text
    # The sequence counter lives in Valkey, not in either process's
    # memory — it kept advancing straight through instance A's death.
    assert seeded_b.json()["delta"]["seq"] == 2

    ws_url = f"ws://127.0.0.1:{instance_b.port}/v1/investigations/{investigation_id}/stream"
    with ws_client.connect(ws_url, additional_headers=headers) as socket_:
        socket_.send('{"last_acknowledged_seq": null}')
        snapshot = socket_.recv()
    assert '"from-a"' in snapshot
    assert '"from-b"' in snapshot


def _seed_node(node_id: str) -> dict[str, object]:
    return {
        "id": node_id,
        "type": "Person",
        "properties": {},
        "provenance": {
            "state": "asserted",
            "sources": [{"document_id": "doc-1", "locator": "p.1", "excerpt_hash": "a" * 64}],
            "first_seen": "2026-01-01T00:00:00+00:00",
        },
        "handling": {
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        "resolution": {},
        "audit": {"created_at": "2026-01-01T00:00:00+00:00", "created_by": "loader-1"},
    }
