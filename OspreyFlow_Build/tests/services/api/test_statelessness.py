"""Statelessness — `spec/03_CONDUIT_MIDDLEWARE.md` §1: "Any Conduit
instance can serve any request for any session; kill one mid-investigation
and the analyst notices nothing." This phase's exit
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

import asyncio
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import warnings
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import websockets.sync.client as ws_client
from cryptography.hazmat.primitives.asymmetric import rsa
from tools.layout import CORE as _REPO

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Provenance, ProvenanceState, SourceRef
from tests.conftest import default_claims, sign_token


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_up(
    base_url: str, *, timeout_s: float = 60.0, process: subprocess.Popen[bytes] | None = None
) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise ConduitExited(f"{base_url} exited ({process.returncode}) before it came up")
        try:
            httpx.get(f"{base_url}/docs", timeout=1.0)
            return
        except httpx.HTTPError as exc:  # noqa: PERF203 - polling loop, not a hot path
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"{base_url} never came up") from last_error


class ConduitStartTime(UserWarning):
    """How long a Conduit took to answer, reported on every start."""


class ConduitExited(TimeoutError):
    """The Conduit's process ended before it answered: said at once, not after the whole wait."""


#: Runs the Conduit as `uvicorn` does, with one addition (GitHub run 43198701543: the second
#: Conduit "never came up" and nothing said why): on SIGUSR1 it writes every asyncio task's stack
#: and every thread's to stderr, so a start-up that hangs says where it waits, not only one that
#: crashes. `--loop asyncio`, so the coroutines are Python's to find.
_LAUNCH = """
import faulthandler, gc, signal, sys, types

def _dump(*_):
    # Every suspended coroutine and async generator, where it waits: a task's own stack stops at
    # the lifespan's async generator, so the frames are found, not walked.
    print("--- at the timeout: where each coroutine waits ---", file=sys.stderr, flush=True)
    for obj in gc.get_objects():
        if isinstance(obj, types.CoroutineType):
            frame = obj.cr_frame
        elif isinstance(obj, types.AsyncGeneratorType):
            frame = obj.ag_frame
        else:
            continue
        if frame is not None:
            code = frame.f_code
            print(f"  {code.co_filename}:{frame.f_lineno} in {code.co_name}", file=sys.stderr)
    print("--- and every thread ---", file=sys.stderr, flush=True)
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    sys.stderr.flush()

signal.signal(signal.SIGUSR1, _dump)
import uvicorn
sys.argv = ["uvicorn", *sys.argv[1:]]
uvicorn.main()
"""


class _ConduitInstance:
    """One real `uvicorn services.api.app:app` process on its own port,
    sharing the ambient ArcadeDB/Valkey/Postgres env with the test."""

    def __init__(self, jwks_url: str, extra_env: dict[str, str] | None = None) -> None:
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        repo_root = _REPO
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
        self._log = tempfile.TemporaryFile()
        env = {
            **os.environ,
            "OIDC_JWKS_URL": jwks_url,
            "OIDC_ALGORITHMS": "RS256",
            "ARCADEDB_DATABASE": "ospreyflow",
            "PYTHONPATH": f"{repo_root}:{packages_root}:{os.environ.get('PYTHONPATH', '')}",
            "ANALYTICS_DB_PATH": str(analytics_db_path),
            **(extra_env or {}),
        }
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _LAUNCH,
                "services.api.app:app",
                "--loop",
                "asyncio",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            env=env,
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            # Kept, not discarded: GitHub run 43198701543's second Conduit "never came up" and
            # nothing said why. Its last lines go into the error below.
            stderr=self._log,
        )
        started = time.monotonic()
        # A deeper root cause than `_spawn_two_instances`'s own list-based cleanup covers: `Popen`
        # above already spawned a real process by the time `_wait_until_up` can fail. If it does,
        # this constructor raises and `self` is never returned to any caller — the process it just
        # started has no reference anywhere a `finally` could reach. Caught and killed here, at
        # the point of failure, rather than relying on a caller that never gets the object back.
        try:
            _wait_until_up(self.base_url, process=self._process)
        except TimeoutError as exc:
            if self._process.poll() is None:
                self._process.send_signal(signal.SIGUSR1)  # where it waits (`_LAUNCH`)
                time.sleep(2)
            self._process.kill()
            self._process.wait(timeout=10)
            self._log.seek(0)
            said = self._log.read().decode("utf-8", "replace")[-20000:]
            self._log.close()
            raise TimeoutError(f"{exc}; the Conduit's own last words:\n{said}") from exc
        except BaseException:
            self.kill()
            self._log.close()
            raise
        # Every start's time, said on every run (a pass included), so a slow second start shows
        # beside the first's in the warnings summary rather than only when it exceeds the wait.
        warnings.warn(
            f"a Conduit came up in {time.monotonic() - started:.1f} s ({self.base_url})",
            ConduitStartTime,
            stacklevel=2,
        )

    def kill(self) -> None:
        """Not `terminate()` — this proves the *second* instance's
        continuity does not depend on the first having shut down
        cleanly, only on the stores it wrote to."""
        if self._process.poll() is None:
            self._process.kill()
            self._process.wait(timeout=10)
        self._log.close()


def _spawn_two_instances(jwks_url: str) -> Iterator[tuple[_ConduitInstance, _ConduitInstance]]:
    """The real bug 18 orphaned processes across two days of runs turned out to be: if the
    *second* `_ConduitInstance`'s own constructor raises (`_wait_until_up`'s timeout, under
    resource contention this session has independently documented elsewhere), the exception fires
    before this function's own `try:` is ever entered — the already-running first instance is
    never referenced in a `finally` at all, not merely killed ungracefully. Accumulating into a
    list as each instance is actually constructed, and tearing down only what the list holds,
    closes that gap: a failure constructing instance two still tears down instance one. A plain
    generator, not the `@pytest.fixture`-decorated one below, so
    `test_a_failed_second_instance_does_not_orphan_the_first` can drive it directly."""
    instances: list[_ConduitInstance] = []
    try:
        instances.append(_ConduitInstance(jwks_url))
        instances.append(_ConduitInstance(jwks_url))
        yield instances[0], instances[1]
    finally:
        for instance in instances:
            instance.kill()  # the process if still running, and its log either way


@pytest.fixture
def two_instances(jwks_url: str) -> Iterator[tuple[_ConduitInstance, _ConduitInstance]]:
    yield from _spawn_two_instances(jwks_url)


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

    # ADR-099 Amendment 12: a case reads exactly one dataset, named or made with it.
    created = httpx.post(
        f"{instance_a.base_url}/v1/investigations",
        headers=headers,
        json={"new_dataset_name": f"Statelessness {new_id()}"},
    )
    assert created.status_code == 201, created.text
    investigation_id = created.json()["id"]
    # ADR-099: the case reads only its own dataset, made with it; what is seeded into it belongs
    # there, as a search result from the case would.
    (own,) = httpx.get(
        f"{instance_a.base_url}/v1/investigations/{investigation_id}/datasets", headers=headers
    ).json()

    # `seed` stores what the Vault holds, read by id (ADR-124 decision 7), so the two people it
    # seeds are written to ArcadeDB first, in the case's dataset; the body posted names the id.
    from_a, from_b = asyncio.run(_write_people(own["id"]))
    seeded_a = httpx.post(
        f"{instance_a.base_url}/v1/investigations/{investigation_id}/seed",
        headers=headers,
        json={"nodes": [_seed_node(from_a, own["id"])], "edges": []},
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
        json={"nodes": [_seed_node(from_b, own["id"])], "edges": []},
    )
    assert seeded_b.status_code == 200, seeded_b.text
    # The sequence counter lives in Valkey, not in either process's
    # memory — it kept advancing straight through instance A's death.
    assert seeded_b.json()["delta"]["seq"] == 2

    ws_url = f"ws://127.0.0.1:{instance_b.port}/v1/investigations/{investigation_id}/stream"
    with ws_client.connect(ws_url, additional_headers=headers) as socket_:
        socket_.send('{"last_acknowledged_seq": null}')
        snapshot = socket_.recv()
    assert f'"{from_a}"' in snapshot
    assert f'"{from_b}"' in snapshot


def test_a_failed_second_instance_does_not_orphan_the_first(
    jwks_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves both fixes by naming the test that would fail. Spawns a real
    first `_ConduitInstance`, forces the second one's own `_wait_until_up` to raise (the real
    failure mode 18 orphaned processes across two days of runs turned out to be), drives
    `_spawn_two_instances` far enough to hit that exception, and asserts *both* processes are
    dead: the first instance's (via `_spawn_two_instances`'s own list-based `finally`) and the
    second, failed instance's own (via `_ConduitInstance.__init__`'s own try/except) — `Popen`
    there runs before `_wait_until_up`, so a failure at that point had already spawned a real
    process that no caller-held reference could otherwise reach."""
    this_module = sys.modules[__name__]
    real_wait_until_up = this_module._wait_until_up
    completed: list[_ConduitInstance] = []
    attempted: list[_ConduitInstance] = []
    real_init = _ConduitInstance.__init__
    calls = {"n": 0}

    def _tracking_init(self: _ConduitInstance, jwks_url_: str) -> None:
        try:
            real_init(self, jwks_url_)
        except Exception:
            attempted.append(self)
            raise
        else:
            completed.append(self)

    def _fail_on_second_call(base_url: str, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise TimeoutError("forced failure for this test")
        real_wait_until_up(base_url, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_ConduitInstance, "__init__", _tracking_init)
    monkeypatch.setattr(this_module, "_wait_until_up", _fail_on_second_call)

    generator = _spawn_two_instances(jwks_url)
    with pytest.raises(TimeoutError):
        next(generator)

    assert len(completed) == 1, "only the first instance should have fully constructed"
    assert len(attempted) == 1, "the second instance's own construction should have failed"

    first_instance, second_attempt = completed[0], attempted[0]
    first_instance._process.wait(timeout=10)
    assert first_instance._process.poll() is not None, (
        "the first instance's own uvicorn process must be dead once the second instance's "
        "construction fails and the generator raises"
    )
    second_attempt._process.wait(timeout=10)
    assert second_attempt._process.poll() is not None, (
        "the second, failed instance's own uvicorn process must already be dead by the time its "
        "own constructor's exception propagates -- Popen ran before _wait_until_up could fail, so "
        "nothing outside __init__ itself ever gets a reference to clean it up"
    )


async def _write_people(dataset_id: str) -> list[str]:
    """Two people written to the Vault in `dataset_id`, OFFICIAL, and their ids."""
    now = datetime.now(UTC)
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())
        tx = await graph.begin_transaction()
        ids = await graph.upsert_nodes(
            [
                NodeWrite(
                    id=new_id(),
                    type="Person",
                    properties={
                        "family_name": f"Statelessnessfixture{new_id()[:8]}",
                        "given_names": "A",
                        "date_of_birth": "1990-01-01",
                    },
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[SourceRef(document_id="fixture", locator="test", excerpt_hash="")],
                        first_seen=now,
                    ),
                    handling=Handling(
                        classification="OFFICIAL",
                        handling_code="P",
                        originator="unit-1",
                        owning_unit="unit-1",
                    ),
                    created_by="test",
                    created_at=now,
                    datasets=[dataset_id],
                )
                for _ in range(2)
            ],
            tx,
        )
        await graph.commit_transaction(tx)
        return list(ids)
    finally:
        await client.aclose()


def _seed_node(node_id: str, dataset_id: str) -> dict[str, object]:
    return {
        "id": node_id,
        "datasets": [dataset_id],
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
