"""Each pytest-xdist worker gets its own stores (admin's T1 part 4, 10 November 2026).

    pytest -p tests.worker_isolation -n 4 --dist loadgroup …

Loaded on the command line, so a run without `-n` is untouched. In a worker (xdist's `config.workerinput`, which a
child process never inherits, unlike `PYTEST_XDIST_WORKER`), at `pytest_configure`, before any test module is imported:

- ArcadeDB: `ArcadeDBConfig.from_env("ospreyflow")` gives `ospreyflow_x<run>_t<started>_gwN`, made here with the deployment's
  schema, as the Conduit makes its own. The name is hard-coded where the
  Conduit, the worker and 21 test call sites open it (`services/api/run_resources.py`, `worker_main.py`), so the
  classmethod is the one place every caller passes through; a per-test `conformance_*` name is left as it is.
- Postgres: `POSTGRES_DB` is `ospreyflow_x<run>_t<started>_gwN`, created here (every store makes its own tables on
  connect).
- Valkey: `VALKEY_DB` is the next free database, flushed here and at the end: N + 1 for a top-level run, after the
  outer run's for a nested one (`OSPREY_WORKER_VALKEY_TAKEN`, which the controller exports to its workers and so to
  their children). At most 15 in all, refused before any worker starts; `-n auto` is given what is left.
- DuckDB, the default analytics engine: `ANALYTICS_DB_PATH` is a file in the worker's own folder.
- The object store: `MINIO_BUCKET_PREFIX` is `ospreyflow-x<run>-t<started>-gwN-`.
- ClickHouse is left alone: its live tests already name their own databases, and `CLICKHOUSE_DATABASE` would override
  those names (`analytics_clickhouse/client.py`'s `from_env`).

At the end each worker removes what it made, each store tried on its own. A killed earlier run's names are swept at
the start of each live run, by the start time in the name (as `adapters/graph_arcadedb/testing.py` does for its own):
only names older than `STALE_AFTER`, longer than any run takes, so a running run's (an outer one's included) are
never dropped.

**What cannot be redirected in-process runs on one worker** (`SERIAL`, as `xdist_group("serial")`, which is why
`--dist loadgroup` is required with `-n`): the tests that start a child process opening `ospreyflow` itself, and the
ones whose Valkey client ignores `VALKEY_DB` (`db=0`, or no `db` at all). During a serial test the in-process
redirect is off too, so the test and its children open the one shared graph; the serial tests run one at a time on
that worker and no other test opens the shared name. The other stores stay the worker's own for a serial test, in
the test and in its children alike, since a child inherits the worker's environment. Valkey's pub/sub channels are
not per database, so they stay shared (investigation ids keep them apart).

**A file that starts real containers runs on one worker too** (`CONTAINERS`, as `xdist_group("containers")`, a group
of its own beside the serial one): one at a time, as in a serial run, so its module's fixtures start once. Its proof is `tests/test_worker_isolation.py` (offline) and
`tests/test_worker_isolation_live.py` (two workers, the same names, on a leased stack).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

#: The name the Conduit and the tests share today, the one redirected per worker.
SHARED = "ospreyflow"
#: The most workers: Valkey has 16 databases (0 to 15) and db 0 stays the serial files' own.
MOST_WORKERS = 15
#: How many Valkey databases (from db 1) the runs enclosing this one have taken.
TAKEN = "OSPREY_WORKER_VALKEY_TAKEN"
#: A name older than this is a killed run's: longer than any run takes (the longest live run measured, about an hour).
STALE_AFTER = 6 * 3600

#: Files that start a child process opening `ospreyflow` (or a fixed folder), run a fixed compose project, or hard-code
#: Valkey's db 0, with why.
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
    "tests/services/api/test_schedule_executor.py": "Valkey(host=config.host, port=config.port): db 0, VALKEY_DB unread",
    "tests/services/api/test_studio_load_stamps_its_case_dataset_live.py": "Valkey(host=..., port=...): db 0",
    "tests/test_worker_isolation_live.py": "its red run's child pytest opens the shared names",
    "tests/harness/test_apply_env.py": "the fixed compose project osprey-local-lite, down -v on 8080/8081",
    "tests/harness/test_six_screen_live_exit.py": "a fixed compose project (COMPOSE_PROJECT), down -v",
    "tests/harness/test_sustained_load.py": "the fixed compose project osprey-local-lite, down -v",
}

#: A file that starts real containers (`docker run -d`, `compose up -d`/`--wait`, a wait for health, or the TLS
#: fixtures' Docker helper). Such files go to one worker of their own, one at a time (`xdist_group("containers")`):
#: under load distribution each worker taking a test from `test_organisation_sign_in.py` started its own module-scoped
#: Keycloak, and on the 16-core server at 8 workers every one "never became ready" (10 November 2026, offline).
CONTAINERS = re.compile(
    r'"run",\s*"-d"|"up",\s*"-d"|"up",\s*"--wait"|\bwait_until_healthy\b|from tests\.harness\.tls_fixtures import'
)
_SOURCES: dict[Path, bool] = {}


def starts_containers(path: Path) -> bool:
    if path not in _SOURCES:
        try:
            _SOURCES[path] = bool(CONTAINERS.search(path.read_text(encoding="utf-8")))
        except OSError:
            _SOURCES[path] = False
    return _SOURCES[path]


_LEFT = re.compile(r"^ospreyflow[_-]x[0-9a-f]{8}[_-]t(\d{10})[_-]gw\d+")


def stale(names: list[str], now: float) -> list[str]:
    """The names a killed run left: this plugin's own shape, and started more than `STALE_AFTER` ago."""
    return [n for n in names if (m := _LEFT.match(n)) and now - int(m.group(1)) >= STALE_AFTER]


def worker_index(worker: str) -> int:
    match = re.fullmatch(r"gw(\d+)", worker)
    if match is None:
        raise pytest.UsageError(f"PYTEST_XDIST_WORKER is gwN, not {worker!r}")
    return int(match.group(1))


def worker_names(worker: str, run: str, started: int, first: int = 1) -> dict[str, str]:
    """The environment one worker runs under: every store's name its own. `first` is the Valkey database of gw0."""
    n = worker_index(worker)
    if first + n > MOST_WORKERS:
        raise pytest.UsageError(f"at most {MOST_WORKERS} workers in all: Valkey has 16 databases, db 0 the serial files'")
    run = run.replace("-", "")[:8].lower()
    return {
        "OSPREY_ARCADEDB_DATABASE": f"{SHARED}_x{run}_t{started}_{worker}",
        "POSTGRES_DB": f"{SHARED}_x{run}_t{started}_{worker}",
        "VALKEY_DB": str(first + n),
        "MINIO_BUCKET_PREFIX": f"{SHARED}-x{run}-t{started}-{worker}-",
    }


#: Where `from_env("ospreyflow")` goes now: the worker's own name, or the shared one during a serial test.
_TARGET: dict[str, str] = {}


def redirect_arcadedb(target: str) -> None:
    """`ArcadeDBConfig.from_env("ospreyflow")` opens `target` instead; any other name is left as it is. The
    parameter keeps its name, since callers pass it by keyword (`from_env(database="ospreyflow")`)."""
    from adapters.graph_arcadedb.client import ArcadeDBConfig

    _TARGET["database"] = target
    original = ArcadeDBConfig.__dict__["from_env"].__func__

    def from_env(cls: type[ArcadeDBConfig], database: str) -> ArcadeDBConfig:
        return cast(ArcadeDBConfig, original(cls, _TARGET["database"] if database == SHARED else database))

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
            names = stale([r["datname"] for r in rows], time.time())
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
            names = stale(await client.list_databases(), time.time())
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


def _buckets(prefix: str | None) -> list[str]:
    """The buckets under `prefix`, or (None) the stale ones."""
    from pyarrow import fs as pa_fs
    from services.ingest.staging import ObjectStorageConfig

    config = ObjectStorageConfig.named("MINIO_BUCKET", "staging")
    s3 = pa_fs.S3FileSystem(
        endpoint_override=config.endpoint, access_key=config.access_key, secret_key=config.secret_key,
        scheme="https" if config.use_ssl else "http", region=config.region, allow_bucket_deletion=True,
    )  # fmt: skip
    found = [i.path for i in s3.get_file_info(pa_fs.FileSelector("", recursive=False))]
    gone = stale(found, time.time()) if prefix is None else [b for b in found if b.startswith(prefix)]
    for bucket in gone:
        s3.delete_dir(bucket)
    return gone


def _live() -> bool:
    """Stores are there to make and clear only on a live run: under a lease (`OSPREY_LANE`), or where a live job says
    so (`OSPREY_WORKER_STORES=1`, the live proof's own inner run, in CI too). An offline run connects to nothing."""
    return bool(os.environ.get("OSPREY_LANE")) or os.environ.get("OSPREY_WORKER_STORES") == "1"


# --- the hooks ----------------------------------------------------------------------------------------------------


class _Worker:
    def __init__(self, worker: str, run: str, first: int) -> None:
        self.admin = os.environ.get("POSTGRES_DB", SHARED)
        self.names = worker_names(worker, run, int(time.time()), first)
        self.folder = Path(tempfile.mkdtemp(prefix=f"osprey-{worker}-"))
        self.made: list[str] = []  # what start() has made, so finish() removes exactly that, even after a failed start

    def start(self) -> None:
        names = self.names
        os.environ.update({k: v for k, v in names.items() if k != "OSPREY_ARCADEDB_DATABASE"})
        os.environ["ANALYTICS_DB_PATH"] = str(self.folder / "analytics.duckdb")
        os.environ["OSPREY_ARCADEDB_DATABASE"] = names["OSPREY_ARCADEDB_DATABASE"]  # for the report, and the tests
        redirect_arcadedb(names["OSPREY_ARCADEDB_DATABASE"])
        if _live():
            self.made.append("valkey")
            _valkey_flush(int(names["VALKEY_DB"]))
            self.made.append("postgres")
            asyncio.run(_postgres(self.admin, names["POSTGRES_DB"]))
            self.made.append("arcadedb")
            asyncio.run(_arcadedb_create(names["OSPREY_ARCADEDB_DATABASE"]))
            self.made.append("buckets")  # made on first use, by the code under test

    def finish(self) -> None:
        """Each store on its own: one that fails to clear does not leave the others behind. The first failure is
        raised once all have been tried."""
        names = self.names
        steps: dict[str, Callable[[], object]] = {
            "arcadedb": lambda: asyncio.run(_arcadedb(names["OSPREY_ARCADEDB_DATABASE"])),
            "postgres": lambda: asyncio.run(_postgres(self.admin, None, drop=[names["POSTGRES_DB"]])),
            "valkey": lambda: _valkey_flush(int(names["VALKEY_DB"])),
            "buckets": lambda: _buckets(names["MINIO_BUCKET_PREFIX"]),
        }
        failures: list[BaseException] = []
        for store in [s for s in steps if s in self.made]:
            try:
                steps[store]()
            except Exception as error:  # noqa: BLE001  (each store tried; the first failure raised below)
                failures.append(error)
        shutil.rmtree(self.folder, ignore_errors=True)
        if failures:
            raise failures[0]


_STATE: dict[str, _Worker] = {}


def _sweep() -> None:
    """What a killed earlier run left: this plugin's names started more than `STALE_AFTER` ago (`stale`)."""
    asyncio.run(_arcadedb(None, left=True))
    asyncio.run(_postgres(os.environ.get("POSTGRES_DB", SHARED), None, left=True))
    _buckets(None)


def _taken() -> int:
    try:
        return int(os.environ.get(TAKEN, "0"))
    except ValueError as error:
        raise pytest.UsageError(f"{TAKEN} is a number of Valkey databases, not {os.environ[TAKEN]!r}") from error


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """`-n auto` on a host with more CPUs than Valkey databases left: as many workers as fit, not a refusal."""
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    return max(1, min(cpus, MOST_WORKERS - _taken()))


def pytest_configure(config: pytest.Config) -> None:
    workerinput = getattr(config, "workerinput", None)  # xdist's own mark of a worker, never inherited by a child
    if workerinput is None:
        workers = len(config.getoption("tx", default=None) or [])  # xdist's own count, after -n auto and --maxprocesses
        if not workers:
            return
        if config.getoption("dist", default="no") != "loadgroup":
            raise pytest.UsageError("tests.worker_isolation needs --dist loadgroup with -n: the serial files share one worker")
        taken = _taken()
        if taken + workers > MOST_WORKERS:
            raise pytest.UsageError(
                f"at most {MOST_WORKERS} workers in all: Valkey has 16 databases, db 0 the serial files'"
                + (f", and the enclosing run took {taken}" if taken else "")
            )
        os.environ[TAKEN] = str(taken + workers)  # the workers inherit it, and so does any run nested in them
        if _live():
            _sweep()
        return
    first = _taken() - int(workerinput["workercount"]) + 1
    state = _Worker(workerinput["workerid"], workerinput.get("testrunuid") or "00000000", first)
    _STATE["worker"] = state  # before start(), so a start that fails part-way is still cleared
    state.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    state = _STATE.pop("worker", None)
    if state is not None:
        state.finish()


def _serial(item: pytest.Item) -> bool:
    extra = {p for p in os.environ.get("OSPREY_WORKER_SERIAL_EXTRA", "").split(os.pathsep) if p}  # the proof's plants
    return _relative(item) in SERIAL or str(Path(str(item.path)).resolve()) in extra


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Before xdist reads the groups (its own hook, in each worker)."""
    for item in items:
        if _serial(item):
            item.add_marker(pytest.mark.xdist_group("serial"))
        elif starts_containers(Path(str(item.path))):
            item.add_marker(pytest.mark.xdist_group("containers"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):  # type: ignore[no-untyped-def]
    """A serial test opens the shared `ospreyflow` in-process too, as its child processes do: one graph, not two. The
    serial tests all run on one worker, one at a time, and no other test opens the shared name."""
    serial = _STATE.get("worker") is not None and _serial(item)
    if serial:
        _TARGET["database"] = SHARED
    try:
        yield
    finally:
        if serial:
            _TARGET["database"] = _STATE["worker"].names["OSPREY_ARCADEDB_DATABASE"]


def _relative(item: pytest.Item) -> str:
    path = Path(str(item.path)).resolve()
    build = Path(__file__).resolve().parents[1]
    try:
        return path.relative_to(build).as_posix()
    except ValueError:
        return path.as_posix()
