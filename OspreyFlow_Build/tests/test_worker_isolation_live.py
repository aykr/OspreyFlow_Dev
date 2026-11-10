"""Two pytest-xdist workers, the same names, one leased stack: neither sees the other's rows (admin's T1 part 4).

A planted file runs under `-n 2` in a subprocess with the lease's ports. Each worker writes the same key in each store
the plugin redirects, the way the Conduit opens it (`ArcadeDBConfig.from_env("ospreyflow")`, `PostgresConfig.from_env()`,
`ValkeyConfig.from_env()`, `s3_bucket("MINIO_BUCKET", "staging")`), waits at a barrier until the other has written,
then reads back what is under that key. With `tests.worker_isolation` each worker finds only its own; without it, the
red, each finds both, in every store. Each worker removes what it wrote, and the plugin removes its databases.

DuckDB's path is a file path, proved distinct offline (`tests/test_worker_isolation.py`); ClickHouse is not redirected.
Live only: listed in the Makefile `test` target's `--ignore` list (`makefile-T1p4.diff`), and run under
`stack_lease.sh`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.store

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"

_PLANTED = '''
import asyncio, json, os, time
from pathlib import Path

import pytest

RUN = os.environ["PYTEST_XDIST_TESTRUNUID"][:8]
WORKER = os.environ["PYTEST_XDIST_WORKER"]
SHARED = Path(os.environ["T1_OUT"])


def _barrier(phase):
    (SHARED / f"{phase}-{WORKER}").touch()
    deadline = time.monotonic() + 120
    while len(list(SHARED.glob(f"{phase}-gw*"))) < 2:
        assert time.monotonic() < deadline, f"the other worker never reached {phase}"
        time.sleep(0.1)


async def _arcadedb(step):
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    kind = f"T1Probe_{RUN}"
    try:
        if step == "write":
            await client.create_database_if_absent()
            try:
                await client.sql(f"CREATE DOCUMENT TYPE {kind} IF NOT EXISTS")
            except Exception:
                pass  # the other worker made it a moment ago (the red run's shared database)
            await client.sql(f"INSERT INTO {kind} SET k = 'same', worker = :w", params={"w": WORKER})
            return None
        if step == "read":
            return sorted({r["worker"] for r in await client.sql(f"SELECT worker FROM {kind} WHERE k = 'same'")})
        await client.sql(f"DELETE FROM {kind} WHERE worker = :w", params={"w": WORKER})
        try:
            await client.sql(f"DROP TYPE {kind} IF EXISTS UNSAFE")
        except Exception:
            pass  # the other worker's removal got there first
    finally:
        await client.aclose()


async def _postgres(step):
    import asyncpg
    from services.api.config import PostgresConfig
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    table = f"t1probe_{RUN}"
    try:
        if step == "write":
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(4242)")
                await conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (k text, worker text)")
            await conn.execute(f"INSERT INTO {table} VALUES ('same', $1)", WORKER)
            return None
        if step == "read":
            return sorted({r["worker"] for r in await conn.fetch(f"SELECT worker FROM {table} WHERE k = 'same'")})
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(4242)")
            await conn.execute(f"DELETE FROM {table} WHERE worker = $1", WORKER)
            left = await conn.fetchval(f"SELECT count(*) FROM {table}")
            if left == 0:
                await conn.execute(f"DROP TABLE {table}")
    finally:
        await conn.close()


def _valkey(step):
    import valkey
    from services.api.config import ValkeyConfig
    client = valkey.Valkey(**ValkeyConfig.from_env().client_kwargs())
    key = f"t1probe:{RUN}"
    try:
        if step == "write":
            client.sadd(key, WORKER)
            return None
        if step == "read":
            return sorted(m.decode() for m in client.smembers(key))
        client.srem(key, WORKER)
    finally:
        client.close()


def _objects(step):
    from pyarrow import fs as pa_fs
    from conduit_common.s3 import s3_bucket
    from services.ingest.staging import ObjectStorageConfig, filesystem
    s3 = filesystem(ObjectStorageConfig.named("MINIO_BUCKET", "staging"))
    folder = f"{s3_bucket('MINIO_BUCKET', 'staging')}/t1probe-{RUN}"
    if step == "write":
        s3.create_dir(folder.split("/")[0])
        with s3.open_output_stream(f"{folder}/{WORKER}") as out:
            out.write(b"same")
        return None
    if step == "read":
        return sorted(i.base_name for i in s3.get_file_info(pa_fs.FileSelector(folder, allow_not_found=True)))
    s3.delete_file(f"{folder}/{WORKER}")


STORES = {
    "arcadedb": lambda step: asyncio.run(_arcadedb(step)),
    "postgres": lambda step: asyncio.run(_postgres(step)),
    "valkey": _valkey,
    "objects": _objects,
}


@pytest.mark.parametrize("side", ["a", "b"])
def test_the_same_key_in_every_store(side):
    seen = {}
    try:
        for write in STORES.values():
            write("write")
        _barrier("written")
        seen = {name: read("read") for name, read in STORES.items()}
        _barrier("read")
    finally:
        for remove in STORES.values():
            remove("remove")
        (SHARED / f"{WORKER}.json").write_text(json.dumps(seen))
'''


def _run(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, dict[str, list[str]]]]:
    (tmp_path / "test_planted.py").write_text(_PLANTED)
    out = tmp_path / "out"
    out.mkdir()
    env = {
        **{k: v for k, v in os.environ.items() if k not in ("PYTEST_ADDOPTS", "OSPREY_STORE_MARK")},
        "T1_OUT": str(out),
        "PYTHONPATH": os.pathsep.join(
            [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
            + [str(BUILD), str(CORE), str(CORE / "packages")]
        ),
    }  # fmt: skip
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", os.devnull, "--rootdir", str(tmp_path),
         *args, str(tmp_path / "test_planted.py")],
        check=False, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    return ran, {p.stem: json.loads(p.read_text()) for p in out.glob("gw*.json")}


STORES = ("arcadedb", "postgres", "valkey", "objects")


@pytest.mark.skipif(not os.environ.get("OSPREY_LANE"), reason="live: under stack_lease.sh only")
def test_two_workers_writing_the_same_names_never_see_each_other_s(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(seen) == ["gw0", "gw1"], (seen, ran.stdout)
    for worker, stores in seen.items():
        assert {s: stores[s] for s in STORES} == {s: [worker] for s in STORES}, (worker, seen)


@pytest.mark.skipif(not os.environ.get("OSPREY_LANE"), reason="live: under stack_lease.sh only")
def test_without_the_plugin_each_worker_sees_both_in_every_store_the_red(tmp_path: Path) -> None:
    """The planted cross-worker leak, caught: the same run on the stack's shared names."""
    ran, seen = _run(tmp_path, "-n", "2")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(seen) == ["gw0", "gw1"], (seen, ran.stdout)
    for worker, stores in seen.items():
        assert {s: stores[s] for s in STORES} == {s: ["gw0", "gw1"] for s in STORES}, (worker, seen)
