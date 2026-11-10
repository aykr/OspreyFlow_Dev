"""Each pytest-xdist worker gets its own stores (admin's T1 part 4, 10 November 2026).

    pytest -p tests.worker_isolation -n 4 --dist loadgroup …

Loaded on the command line, so a run without `-n` is untouched. In a worker (`PYTEST_XDIST_WORKER` is `gwN`), at
`pytest_configure`, before any test module is imported:

- ArcadeDB: `ArcadeDBConfig.from_env("ospreyflow")` gives `ospreyflow_x<run>_gwN`, made here with the deployment's
  schema, as the Conduit makes its own. The name is hard-coded where the
  Conduit, the worker and 21 test call sites open it (`services/api/run_resources.py`, `worker_main.py`), so the
  classmethod is the one place every caller passes through; a per-test `conformance_*` name is left as it is.
- Postgres: `POSTGRES_DB` is `ospreyflow_x<run>_gwN`, created here (every store makes its own tables on connect).
- Valkey: `VALKEY_DB` is N + 1 (at most 15 workers), flushed here and at the end.
- DuckDB, the default analytics engine: `ANALYTICS_DB_PATH` is a file in the worker's own folder.
- The object store: `MINIO_BUCKET_PREFIX` is `ospreyflow-x<run>-gwN-`.
- ClickHouse is left alone: its live tests already name their own databases, and `CLICKHOUSE_DATABASE` would override
  those names (`analytics_clickhouse/client.py`'s `from_env`).

At the end each worker removes what it made. The controller first removes what a killed earlier run left behind
(`*_x*_gw*` names only; the leased stack is the lane's own).

**What cannot be redirected in-process runs on one worker** (`SERIAL`, as `xdist_group("serial")`, which is why
`--dist loadgroup` is required with `-n`): the tests that start a child process that opens `ospreyflow` itself, and the
ones that hard-code `Valkey(db=0)`. Its proof is `tests/test_worker_isolation.py` (offline) and
`tests/test_worker_isolation_live.py` (two workers, the same names, on a leased stack).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import cast

import pytest

#: The name the Conduit and the tests share today, the one redirected per worker.
SHARED = "ospreyflow"
#: The most workers: Valkey has 16 databases (0 to 15) and db 0 stays the serial files' own.
MOST_WORKERS = 15

#: Files that start a child process opening `ospreyflow` (or a fixed folder), or that hard-code Valkey's db 0, with why.
SERIAL = {
    "tests/services/api/test_statelessness.py": "two uvicorn Conduits, which open ArcadeDB's ospreyflow themselves",
    "tests/services/api/test_statelessness_clickhouse.py": "the same two uvicorn Conduits",
    "tests/ingest/test_pid_seed_live.py": "runs scripts.seed_pid (ospreyflow) in a child, with a fixed scratch folder",
    "tests/resolve/test_trigger.py": "Valkey(host='localhost', port=6379, db=0)",
    "tests/scenarios/test_phase6_extraction_and_resolution.py": "Valkey(..., db=0)",
    "tests/services/api/test_ws_ticket.py": "Valkey(..., db=0)",
    "tests/services/api/test_worker.py": "Valkey(..., db=0)",
    "tests/services/api/test_revoked_principal_precheck.py": "ValkeyConfig(..., db=0)",
    "tests/services/api/test_valkey_store.py": "Valkey(host='localhost', port=port, db=0)",
}

_LEFT = re.compile(r"^ospreyflow[_-]x[0-9a-f]{8}[_-]gw\d+")


def worker_index(worker: str) -> int:
    match = re.fullmatch(r"gw(\d+)", worker)
    if match is None:
        raise pytest.UsageError(f"PYTEST_XDIST_WORKER is gwN, not {worker!r}")
    return int(match.group(1))


def worker_names(worker: str, run: str) -> dict[str, str]:
    """The environment one worker runs under: every store's name its own."""
    n = worker_index(worker)
    if n + 1 > MOST_WORKERS:
        raise pytest.UsageError(f"at most {MOST_WORKERS} workers: Valkey has 16 databases, db 0 the serial files'")
    run = run.replace("-", "")[:8].lower()
    return {
        "OSPREY_ARCADEDB_DATABASE": f"{SHARED}_x{run}_{worker}",
        "POSTGRES_DB": f"{SHARED}_x{run}_{worker}",
        "VALKEY_DB": str(n + 1),
        "MINIO_BUCKET_PREFIX": f"{SHARED}-x{run}-{worker}-",
    }


def redirect_arcadedb(target: str) -> None:
    """`ArcadeDBConfig.from_env("ospreyflow")` opens `target` instead; any other name is left as it is. The
    parameter keeps its name, since callers pass it by keyword (`from_env(database="ospreyflow")`)."""
    from adapters.graph_arcadedb.client import ArcadeDBConfig

    original = ArcadeDBConfig.__dict__["from_env"].__func__

    def from_env(cls: type[ArcadeDBConfig], database: str) -> ArcadeDBConfig:
        return cast(ArcadeDBConfig, original(cls, target if database == SHARED else database))

    from_env.__wrapped__ = original  # type: ignore[attr-defined]
    ArcadeDBConfig.from_env = classmethod(from_env)  # type: ignore[method-assign,assignment]


# --- the stores ---------------------------------------------------------------------------------------------------


async def _postgres(admin: str, create: str | None, drop: list[str] | None = None, left: bool = False) -> list[str]:
    """Run from `admin`, the database the stack was given (never the one being dropped)."""
    import dataclasses

    import asyncpg
    from services.api.config import PostgresConfig

    config = dataclasses.replace(PostgresConfig.from_env(), database=admin)
    conn = await asyncpg.connect(config.dsn)
    try:
        names = drop or []
        if left:
            rows = await conn.fetch("SELECT datname FROM pg_database")
            names = [r["datname"] for r in rows if _LEFT.match(r["datname"])]
        for name in names:
            await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        if create:
            await conn.execute(f'DROP DATABASE IF EXISTS "{create}" WITH (FORCE)')
            await conn.execute(f'CREATE DATABASE "{create}"')
        return names
    finally:
        await conn.close()


async def _arcadedb_create(database: str) -> None:
    """The worker's graph, made as the Conduit makes its own (`run_resources.build_run_resources`): a test that reads
    `ospreyflow` before any Conduit has started in its worker finds the schema there, as it does on the stack."""
    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme
    from ontology.packs import load_deployment_ontology

    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        await client.drop_database_named(database)
        await client.create_database_if_absent()
        await GraphArcadeDBAdapter(client, load_uk_le_scheme()).apply_schema(load_deployment_ontology())
    finally:
        await client.aclose()


async def _arcadedb(drop: str | None, left: bool = False) -> list[str]:
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig

    client = ArcadeDBClient(ArcadeDBConfig.from_env("worker-isolation-control"))
    try:
        names = [drop] if drop else []
        if left:
            names = [d for d in await client.list_databases() if _LEFT.match(d)]
        for name in names:
            await client.drop_database_named(name)
        return names
    finally:
        await client.aclose()


def _valkey_flush(db: int) -> None:
    import valkey
    from services.api.config import ValkeyConfig

    kwargs = {**ValkeyConfig.from_env().client_kwargs(), "db": db}
    client = valkey.Valkey(**kwargs, socket_connect_timeout=5)
    try:
        client.flushdb()
    finally:
        client.close()  # type: ignore[no-untyped-call]


def _buckets(prefix_pattern: re.Pattern[str] | str) -> list[str]:
    from pyarrow import fs as pa_fs
    from services.ingest.staging import ObjectStorageConfig

    config = ObjectStorageConfig.named("MINIO_BUCKET", "staging")
    s3 = pa_fs.S3FileSystem(
        endpoint_override=config.endpoint, access_key=config.access_key, secret_key=config.secret_key,
        scheme="https" if config.use_ssl else "http", region=config.region, allow_bucket_deletion=True,
    )  # fmt: skip
    found = [i.path for i in s3.get_file_info(pa_fs.FileSelector("", recursive=False))]
    gone = [b for b in found if (prefix_pattern.match(b) if isinstance(prefix_pattern, re.Pattern) else b.startswith(prefix_pattern))]
    for bucket in gone:
        s3.delete_dir(bucket)
    return gone


def _live() -> bool:
    """A store is there to isolate only under a lease (offline runs connect to nothing)."""
    return bool(os.environ.get("OSPREY_LANE"))


# --- the hooks ----------------------------------------------------------------------------------------------------


class _Worker:
    def __init__(self, worker: str, run: str) -> None:
        self.admin = os.environ.get("POSTGRES_DB", SHARED)
        self.names = worker_names(worker, run)
        self.folder = Path(tempfile.mkdtemp(prefix=f"osprey-{worker}-"))

    def start(self) -> None:
        names = self.names
        os.environ.update({k: v for k, v in names.items() if k != "OSPREY_ARCADEDB_DATABASE"})
        os.environ["ANALYTICS_DB_PATH"] = str(self.folder / "analytics.duckdb")
        os.environ["OSPREY_ARCADEDB_DATABASE"] = names["OSPREY_ARCADEDB_DATABASE"]  # for the report, and the tests
        redirect_arcadedb(names["OSPREY_ARCADEDB_DATABASE"])
        if _live():
            asyncio.run(_postgres(self.admin, names["POSTGRES_DB"]))
            asyncio.run(_arcadedb_create(names["OSPREY_ARCADEDB_DATABASE"]))
            _valkey_flush(int(names["VALKEY_DB"]))

    def finish(self) -> None:
        names = self.names
        try:
            if _live():
                asyncio.run(_arcadedb(names["OSPREY_ARCADEDB_DATABASE"]))
                asyncio.run(_postgres(self.admin, None, drop=[names["POSTGRES_DB"]]))
                _valkey_flush(int(names["VALKEY_DB"]))
                _buckets(names["MINIO_BUCKET_PREFIX"])
        finally:
            shutil.rmtree(self.folder, ignore_errors=True)


_STATE: dict[str, _Worker] = {}


def pytest_configure(config: pytest.Config) -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    workers = config.getoption("numprocesses", default=None)
    if worker is None:
        if workers and config.getoption("dist", default="no") != "loadgroup":
            raise pytest.UsageError("tests.worker_isolation needs --dist loadgroup with -n: the serial files share one worker")
        if workers and _live():  # the controller: what a killed earlier run left
            asyncio.run(_arcadedb(None, left=True))
            asyncio.run(_postgres(os.environ.get("POSTGRES_DB", SHARED), None, left=True))
            _buckets(re.compile(r"^ospreyflow-x[0-9a-f]{8}-gw\d+-"))
        return
    state = _Worker(worker, os.environ.get("PYTEST_XDIST_TESTRUNUID", "00000000"))
    state.start()
    _STATE["worker"] = state


def pytest_unconfigure(config: pytest.Config) -> None:
    state = _STATE.pop("worker", None)
    if state is not None:
        state.finish()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Before xdist reads the groups (its own hook, in each worker)."""
    for item in items:
        if _relative(item) in SERIAL:
            item.add_marker(pytest.mark.xdist_group("serial"))


def _relative(item: pytest.Item) -> str:
    path = Path(str(item.path)).resolve()
    build = Path(__file__).resolve().parents[1]
    try:
        return path.relative_to(build).as_posix()
    except ValueError:
        return path.as_posix()
