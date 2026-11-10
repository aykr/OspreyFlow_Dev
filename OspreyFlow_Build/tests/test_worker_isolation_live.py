"""Two pytest-xdist workers, the same names, one leased stack: neither sees the other's rows (admin's T1 part 4).

A planted file runs under `-n 2` in a subprocess with the lease's ports. Each worker writes the same key in each store
the plugin redirects, the way the Conduit opens it (`ArcadeDBConfig.from_env("ospreyflow")`, `PostgresConfig.from_env()`,
`ValkeyConfig.from_env()`, `s3_bucket("MINIO_BUCKET", "staging")`), waits at a barrier until the other has written,
then reads back what is under that key. With `tests.worker_isolation` each worker finds only its own; without it, the
red, each finds both, in every store. Each worker removes what it wrote, and the plugin removes its databases; afterwards the outer test checks that
nothing of the inner run's is left in any store (`_left_behind`). In the red run the two workers share one database and
one bucket, so each makes what is missing in turn, gw0 first, and the maker removes it once both have removed theirs.

DuckDB's path is a file path, proved distinct offline (`tests/test_worker_isolation.py`); ClickHouse is not redirected.
Live only: under `stack_lease.sh`, or CI's `conformance` job; in the Makefile `test` target's `--ignore` list and
that job's list (`makefile-T1p4.diff`, `ci-yml-T1p4.diff`, to land with the merge). Inside an outer `-n` run it is
serial, and its inner workers take the Valkey databases after the outer run's.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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
        if step == "prepare":
            if client._config.database not in await client.list_databases():
                await client.create_database_if_absent()
                (SHARED / f"made-arcadedb-{WORKER}").touch()  # the red run made the stack's shared one: removed after
            return None
        if step == "write":
            try:
                await client.sql(f"CREATE DOCUMENT TYPE {kind} IF NOT EXISTS")
            except Exception:
                pass  # the other worker is making it (the red run's shared database): wait until it is there
            deadline = time.monotonic() + 30
            while not await client.sql("SELECT FROM schema:types WHERE name = :n", params={"n": kind}):
                assert time.monotonic() < deadline, f"{kind} never appeared"
                await asyncio.sleep(0.1)
            await client.sql(f"INSERT INTO {kind} SET k = 'same', worker = :w", params={"w": WORKER})
            return None
        if step == "read":
            return sorted({r["worker"] for r in await client.sql(f"SELECT worker FROM {kind} WHERE k = 'same'")})
        if await client.sql("SELECT FROM schema:types WHERE name = :n", params={"n": kind}):
            await client.sql(f"DELETE FROM {kind} WHERE worker = :w", params={"w": WORKER})
        # Both workers' rows gone before the type (and a database the red run made) is dropped: in the red run they
        # share one, and a type dropped under the other worker's DELETE fails it (seen on stack b, 10 November).
        _barrier("arcadedb-removed")
        try:
            await client.sql(f"DROP TYPE {kind} IF EXISTS UNSAFE")
        except Exception:
            pass  # the other worker's drop got there first
        if (SHARED / f"made-arcadedb-{WORKER}").exists():
            await client.drop_database()
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
            if await conn.fetchval("SELECT to_regclass($1)", table) is None:
                return None  # never made: this worker's write failed first
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
    bucket = folder.split("/")[0]
    if step == "prepare":
        if s3.get_file_info(bucket).type == pa_fs.FileType.NotFound:
            s3.create_dir(bucket)
            (SHARED / f"made-bucket-{WORKER}").touch()
        return None
    if step == "write":
        with s3.open_output_stream(f"{folder}/{WORKER}") as out:
            out.write(b"same")
        return None
    if step == "read":
        return sorted(i.base_name for i in s3.get_file_info(pa_fs.FileSelector(folder, allow_not_found=True)))
    if s3.get_file_info(f"{folder}/{WORKER}").type != pa_fs.FileType.NotFound:
        s3.delete_file(f"{folder}/{WORKER}")
    if s3.get_file_info(folder).type != pa_fs.FileType.NotFound and not s3.get_file_info(pa_fs.FileSelector(folder)):
        s3.delete_dir(folder)
    _barrier("objects-removed")  # both workers' objects gone before the bucket the red run made is
    if (SHARED / f"made-bucket-{WORKER}").exists():
        from services.api.object_transfer import store_from_env
        store_from_env(allow_bucket_deletion=True).delete_dir(bucket)


STORES = {
    "arcadedb": lambda step: asyncio.run(_arcadedb(step)),
    "postgres": lambda step: asyncio.run(_postgres(step)),
    "valkey": _valkey,
    "objects": _objects,
}


def _prepare():
    """Each worker makes what is missing in turn, gw0 first: in the red run the two share one database and one
    bucket, and two that both found it absent would both make it and both drop it."""
    if WORKER != "gw0":
        _barrier_on("prepared-gw0")
    for prepare in (STORES["arcadedb"], STORES["objects"]):
        prepare("prepare")
    (SHARED / f"prepared-{WORKER}").touch()
    _barrier("prepared")


def _barrier_on(name):
    deadline = time.monotonic() + 120
    while not (SHARED / name).exists():
        assert time.monotonic() < deadline, f"{name} never came"
        time.sleep(0.1)


def _names():
    from adapters.graph_arcadedb.client import ArcadeDBConfig
    from conduit_common.s3 import s3_bucket
    from services.api.config import PostgresConfig, ValkeyConfig
    return {
        "run": RUN,
        "arcadedb": ArcadeDBConfig.from_env(database="ospreyflow").database,
        "postgres": PostgresConfig.from_env().database,
        "valkey": ValkeyConfig.from_env().db,
        "bucket": s3_bucket("MINIO_BUCKET", "staging"),
    }


@pytest.mark.parametrize("side", ["a", "b"])
def test_the_same_key_in_every_store(side):
    seen = {"names": _names()}
    try:
        _prepare()
        for write in STORES.values():
            write("write")
        _barrier("written")
        seen.update({name: read("read") for name, read in STORES.items()})  # keeping "names", for the check after
        _barrier("read")
    finally:
        failures = []
        for remove in STORES.values():  # each store on its own: one that fails does not leave the others behind
            try:
                remove("remove")
            except Exception as error:
                failures.append(error)
        (SHARED / f"{WORKER}.json").write_text(json.dumps(seen))
        assert not failures, failures
'''


def _run(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, dict[str, Any]]]:
    (tmp_path / "test_planted.py").write_text(_PLANTED)
    out = tmp_path / "out"
    out.mkdir()
    env = {
        **{k: v for k, v in os.environ.items()
           if k not in ("PYTEST_ADDOPTS", "OSPREY_STORE_MARK") and not k.startswith("PYTEST_XDIST_")},
        "T1_OUT": str(out),
        "OSPREY_WORKER_STORES": "1",
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

#: Under a lease, or in CI's conformance job (the one job with stores, which alone names its ArcadeDB container);
#: never CI's `test` job, which sets `CI` too but has no stores.
_LIVE = pytest.mark.skipif(
    not os.environ.get("OSPREY_LANE")
    and not (os.environ.get("CI", "").lower() == "true" and os.environ.get("OSPREY_TEST_ARCADEDB_CONTAINER")),
    reason="live: under stack_lease.sh, or CI's conformance job",
)


def _left_behind(seen: dict[str, dict[str, Any]]) -> list[str]:
    """What the inner run left on the stack under its own names: each worker's databases, Valkey db and buckets (the
    plugin's to remove), and the probe's type, table, key and folder (the planted file's). Rule 12: teardown is
    claimed, so it is checked."""
    import asyncio

    import asyncpg
    import valkey
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from services.api.config import PostgresConfig, ValkeyConfig
    from services.api.object_transfer import store_from_env

    names = [stores["names"] for stores in seen.values()]
    run = {n["run"] for n in names}.pop()
    left: list[str] = []

    async def graph_and_tables() -> None:
        client = ArcadeDBClient(ArcadeDBConfig.from_env(database="worker-isolation-check"))
        try:
            databases = await client.list_databases()
            left.extend(f"arcadedb {n['arcadedb']}" for n in names if n["arcadedb"] != "ospreyflow" and n["arcadedb"] in databases)
            for database in {n["arcadedb"] for n in names} & set(databases):
                shared = ArcadeDBClient(ArcadeDBConfig.from_env(database=str(database)))
                try:
                    if await shared.sql("SELECT FROM schema:types WHERE name = :n", params={"n": f"T1Probe_{run}"}):
                        left.append(f"arcadedb type T1Probe_{run} in {database}")
                finally:
                    await shared.aclose()
        finally:
            await client.aclose()
        conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
        try:
            have = {r["datname"] for r in await conn.fetch("SELECT datname FROM pg_database")}
            left.extend(f"postgres {n['postgres']}" for n in names if n["postgres"] != os.environ.get("POSTGRES_DB", "ospreyflow") and n["postgres"] in have)
            if await conn.fetchval("SELECT to_regclass($1)", f"t1probe_{run}") is not None:
                left.append(f"postgres table t1probe_{run}")
        finally:
            await conn.close()

    asyncio.run(graph_and_tables())
    for db in {int(n["valkey"]) for n in names}:
        client = valkey.Valkey(**{**ValkeyConfig.from_env().client_kwargs(), "db": db})
        try:
            if client.exists(f"t1probe:{run}"):
                left.append(f"valkey t1probe:{run} in db {db}")
            if db != 0 and client.dbsize():
                left.append(f"valkey db {db} not flushed")
        finally:
            client.close()  # type: ignore[no-untyped-call]
    s3 = store_from_env()
    from pyarrow import fs as pa_fs

    for bucket in {str(n["bucket"]) for n in names}:
        if s3.get_file_info(f"{bucket}/t1probe-{run}").type != pa_fs.FileType.NotFound:
            left.append(f"objects {bucket}/t1probe-{run}")
        elif "-x" in bucket and s3.get_file_info(bucket).type != pa_fs.FileType.NotFound:
            left.append(f"bucket {bucket}")
    return left


@_LIVE
def test_two_workers_writing_the_same_names_never_see_each_other_s(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(seen) == ["gw0", "gw1"], (seen, ran.stdout)
    for worker, stores in seen.items():
        assert {s: stores[s] for s in STORES} == {s: [worker] for s in STORES}, (worker, seen)
    assert _left_behind(seen) == []


@_LIVE
def test_without_the_plugin_each_worker_sees_both_in_every_store_the_red(tmp_path: Path) -> None:
    """The planted cross-worker leak, caught: the same run on the stack's shared names."""
    ran, seen = _run(tmp_path, "-n", "2")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(seen) == ["gw0", "gw1"], (seen, ran.stdout)
    for worker, stores in seen.items():
        assert {s: stores[s] for s in STORES} == {s: ["gw0", "gw1"] for s in STORES}, (worker, seen)
    assert _left_behind(seen) == []
