"""`tests/worker_isolation.py`, each pytest-xdist worker's own stores, offline (admin's T1 part 4, 10 November 2026).

A planted file runs under `-n 2` in a subprocess, on the closed offline ports (59991 to 59994), and each test writes down
the names its worker's code would open, from the same calls the Conduit makes (`ArcadeDBConfig.from_env("ospreyflow")`,
`PostgresConfig`, `ValkeyConfig`, `s3_bucket`, the analytics path). Red if two workers would open the same name in any
store, as they do without the plugin; if a per-test `conformance_*` name is rewritten; if a serial file is not grouped;
or if a live file starts a child process or hard-codes Valkey's db 0 and is not in `SERIAL`. The live proof, two workers
writing the same keys on a leased stack, is `tests/test_worker_isolation_live.py`.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"

_PLANTED = '''
import json, os, time
from pathlib import Path

import pytest

def _names():
    from adapters.graph_arcadedb.client import ArcadeDBConfig
    from conduit_common.s3 import s3_bucket
    from services.api.config import PostgresConfig, ValkeyConfig
    return {
        "arcadedb": ArcadeDBConfig.from_env(database="ospreyflow").database,
        "arcadedb_positional": ArcadeDBConfig.from_env("ospreyflow").database,
        "conformance": ArcadeDBConfig.from_env(database="conformance_1_abc").database,
        "postgres": PostgresConfig.from_env().database,
        "valkey": ValkeyConfig.from_env().db,
        "bucket": s3_bucket("MINIO_BUCKET", "staging"),
        "analytics": os.environ.get("ANALYTICS_DB_PATH", "the default"),
        "taken": os.environ.get("OSPREY_WORKER_VALKEY_TAKEN"),
    }

@pytest.mark.parametrize("i", range(8))
def test_names(i):
    time.sleep(0.2)  # long enough that both workers take some
    worker = os.environ.get("PYTEST_XDIST_WORKER", "none")
    out = Path(os.environ["T1_OUT"]) / f"{worker}.json"
    out.write_text(json.dumps(_names()))
'''


def _env(out: Path, **extra: str) -> dict[str, str]:
    drop = ("OSPREY_LANE", "PYTEST_ADDOPTS", "OSPREY_STORE_MARK", "POSTGRES_DB", "VALKEY_DB", "MINIO_BUCKET_PREFIX",
            "ANALYTICS_DB_PATH", "MINIO_BUCKET", "OSPREY_WORKER_VALKEY_TAKEN")  # fmt: skip  (a top-level run unless set)
    return {
        **{k: v for k, v in os.environ.items() if k not in drop and not k.startswith("PYTEST_XDIST_")},
        "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994",
        "T1_OUT": str(out),
        "PYTHONPATH": os.pathsep.join([str(BUILD), str(CORE), str(CORE / "packages")]),
        **extra,
    }  # fmt: skip


def _run(
    tmp_path: Path, *args: str, files: tuple[str, ...] = ("test_planted.py",), **extra: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, dict[str, Any]]]:
    (tmp_path / "test_planted.py").write_text(_PLANTED)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", os.devnull, "--rootdir", str(tmp_path),
         *args, *(str(tmp_path / f) for f in files)],
        check=False, cwd=tmp_path, env=_env(out, **extra), capture_output=True, text=True, timeout=180,
    )  # fmt: skip
    return ran, {p.stem: json.loads(p.read_text()) for p in out.glob("*.json")}


STORES = ("arcadedb", "arcadedb_positional", "postgres", "valkey", "bucket", "analytics")


def test_two_workers_open_different_names_in_every_store(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(seen) == ["gw0", "gw1"], (seen, ran.stdout)
    for store in STORES:
        assert seen["gw0"][store] != seen["gw1"][store], (store, seen)
    for worker, names in seen.items():
        assert names["conformance"] == "conformance_1_abc", "a per-test name was rewritten"
        assert names["arcadedb"] == names["arcadedb_positional"] == names["postgres"]
        assert re.fullmatch(rf"ospreyflow_x[0-9a-f]{{8}}_t[0-9]{{10}}_{worker}", names["arcadedb"]), names
        assert names["valkey"] == int(worker[2:]) + 1 and names["valkey"] != 0
        assert names["taken"] == "2", "the controller exports the databases its workers took, for a run nested in one"
        assert names["bucket"].startswith("ospreyflow-x") and names["bucket"].endswith(f"-{worker}-staging"), names


def test_without_the_plugin_two_workers_share_every_name_the_red(tmp_path: Path) -> None:
    """The leak the plugin closes, shown: the same planted run with the plugin left out."""
    ran, seen = _run(tmp_path, "-n", "2")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(seen) == ["gw0", "gw1"], (seen, ran.stdout)
    for store in STORES:
        assert seen["gw0"][store] == seen["gw1"][store], (store, seen)
    assert seen["gw0"]["arcadedb"] == "ospreyflow" and seen["gw0"]["valkey"] == 0


def test_a_run_without_n_is_left_as_it_is(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert seen["none"]["arcadedb"] == "ospreyflow" and seen["none"]["valkey"] == 0


def test_n_without_loadgroup_is_refused(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2")
    assert ran.returncode != 0 and "needs --dist loadgroup" in ran.stdout + ran.stderr
    assert seen == {}


def test_more_workers_than_valkey_has_databases_is_refused() -> None:
    from tests.worker_isolation import worker_names

    assert worker_names("gw14", "abcdef12", 1_700_000_000)["VALKEY_DB"] == "15"
    with pytest.raises(pytest.UsageError, match="at most 15 workers"):
        worker_names("gw15", "abcdef12", 1_700_000_000)
    assert worker_names("gw1", "abcdef12", 1_700_000_000, first=13)["VALKEY_DB"] == "14"
    with pytest.raises(pytest.UsageError, match="at most 15 workers"):
        worker_names("gw3", "abcdef12", 1_700_000_000, first=13)


def test_a_worker_id_not_of_xdist_s_shape_is_refused() -> None:
    from tests.worker_isolation import worker_index

    assert worker_index("gw12") == 12
    for wrong in ("master", "gw", "gw1a", "1"):
        with pytest.raises(pytest.UsageError, match="gwN"):
            worker_index(wrong)


def test_each_serial_file_exists_and_is_grouped() -> None:
    from tests.worker_isolation import SERIAL, pytest_collection_modifyitems

    class _Item:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.marks: list[pytest.MarkDecorator] = []

        def add_marker(self, mark: pytest.MarkDecorator) -> None:
            self.marks.append(mark)

    items = [_Item(BUILD / rel) for rel in SERIAL] + [_Item(BUILD / "tests/services/api/test_route_rights.py")]
    pytest_collection_modifyitems(None, items)  # type: ignore[arg-type]
    for item in items[:-1]:
        assert item.path.exists(), item.path
        assert [m.mark.args for m in item.marks] == [("serial",)], item.path
    assert items[-1].marks == []


#: What only a separate process would reach, or what is one per machine: the shapes `SERIAL` exists for, besides
#: Valkey's db 0. A child Conduit, seeder, CLI or pytest (`-m services.…`, `scripts.…`, `cli`, `pytest`, uvicorn);
#: a compose project (`docker compose -p <name>`, one per machine whatever the worker, `down -v` on its ports); a
#: multiprocessing child (spawned, it never sees the in-process redirect).
_CHILD = re.compile(
    r"services\.api\.app:app|\"-m\",\s*\"(?:pytest|uvicorn|services\.|scripts\.|cli\b)"
    r"|\bscripts\.seed_pid\b|\"compose\",[^\]]*?\"(?:-p|--project-name)\"|\bmultiprocessing\b|ProcessPoolExecutor"
)


def _valkey_db_0(source: str) -> bool:
    """A `Valkey(...)` call that opens db 0 whatever `VALKEY_DB` says: `db=0`, or no `db` and no `**kwargs` that could
    carry one (`test_schedule_executor.py`'s `Valkey(host=config.host, port=config.port)`). Read from the syntax tree,
    since a `db=int(os.environ.get(...))` holds parentheses a pattern cannot follow."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name not in ("Valkey", "ValkeyConfig"):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        db = keywords.get("db")
        if db is None and len(node.args) >= 3:  # Valkey(host, port, db) and ValkeyConfig(host, port, db)
            db = node.args[2]
        unpacked = keywords.get(None)
        if db is None and isinstance(unpacked, ast.Dict):  # Valkey(**{**config.client_kwargs(), "db": 0})
            pairs = dict(zip(unpacked.keys, unpacked.values, strict=True))
            db = next((v for k, v in pairs.items() if isinstance(k, ast.Constant) and k.value == "db"), None)
        if db is None and None in keywords:  # **kwargs that may carry one
            continue
        if db is None and name == "Valkey" or isinstance(db, ast.Constant) and db.value == 0:
            return True
    return False


def unserialised(files: list[str]) -> list[str]:
    from tests.worker_isolation import SERIAL

    found = []
    for rel in files:
        source = (BUILD / rel).read_text(encoding="utf-8")
        if rel not in SERIAL and (_CHILD.search(source) or _valkey_db_0(source)):
            found.append(rel)
    return found


def test_every_live_file_that_starts_a_conduit_or_seeder_or_uses_valkey_db_0_is_serial() -> None:
    from tools.live_select import Repo

    assert unserialised(Repo().live_set()) == []


def test_the_serial_check_names_a_file_that_should_be_serial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Its red, in the shapes the live files take: a uvicorn Conduit, the seeder, a child pytest, Valkey's db 0 named
    and Valkey given no db; a client given `VALKEY_DB`'s db, and the in-process scale seeder, are not serial."""
    monkeypatch.setattr(sys.modules[__name__], "BUILD", tmp_path)
    (tmp_path / "tests").mkdir()
    shapes = {
        "tests/test_a.py": 'cmd = [sys.executable, "-m", "uvicorn", "services.api.app:app"]\n',
        "tests/test_b.py": 'subprocess.run([sys.executable, "-m", "scripts.seed_pid", "reset"])\n',
        "tests/test_c.py": 'client = Valkey(host="localhost", port=6379, db=0)\n',
        "tests/test_d.py": 'client = Valkey(**ValkeyConfig.from_env().client_kwargs())\n',
        "tests/test_e.py": "from scripts.seed_pid_scale import seed_scale  # in-process, its own database\n",
        "tests/test_f.py": "client = Valkey(\n    host=config.host,\n    port=config.port,\n)\n",
        "tests/test_g.py": 'ran = subprocess.run([sys.executable, "-m", "pytest", str(path)])\n',
        "tests/test_h.py": "client = Valkey(host=config.host, port=config.port, db=config.db)\n",
        "tests/test_i.py": 'client = Valkey(\n    host=h,\n    port=int(os.environ.get("VALKEY_PORT", "6379")),\n    db=int(os.environ.get("VALKEY_DB", "0")),\n)\n',
        "tests/test_j.py": "config = ValkeyConfig(host='localhost', port=6379, db=0)\n",
        "tests/test_k.py": 'client = valkey.Valkey(**{**ValkeyConfig.from_env().client_kwargs(), "db": 0})\n',
        "tests/test_l.py": "config = ValkeyConfig('localhost', 6379, 0)\n",
        "tests/test_m.py": 'subprocess.run(["docker", "compose", "-p", LOCAL_LITE_PROJECT, "ps"])\n',
        "tests/test_n.py": 'ctx = multiprocessing.get_context("spawn")\n',
        "tests/test_o.py": 'subprocess.run([sys.executable, "-m", "scripts.make_home_cases"])\n',
        "tests/test_p.py": 'subprocess.run([sys.executable, "-m", "cli", "status"])\n',
        "tests/test_q.py": 'client = valkey.Valkey(**{**ValkeyConfig.from_env().client_kwargs(), "db": cfg.db})\n',
        "tests/test_r.py": 'subprocess.run(["docker", "compose", "--project-name", PROJECT, "ps"])\n',
        "tests/test_s.py": 'cmd = ["docker", "compose", "-f",\n       str(folder / "compose.yaml"), "-p", NAME, "ps"]\n',
        "tests/test_t.py": 'subprocess.run(["docker", "compose", "version"])\n',
    }
    for rel, text in shapes.items():
        (tmp_path / rel).write_text(text)
    assert unserialised(list(shapes)) == [
        "tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_f.py", "tests/test_g.py", "tests/test_j.py",
        "tests/test_k.py", "tests/test_l.py", "tests/test_m.py", "tests/test_n.py", "tests/test_o.py", "tests/test_p.py",
        "tests/test_r.py", "tests/test_s.py",
    ]  # fmt: skip


_SERIAL_PLANTED = """
import json, os, time
from pathlib import Path

import pytest

@pytest.mark.parametrize("i", range(6))
def test_one(i):
    from adapters.graph_arcadedb.client import ArcadeDBConfig
    from services.api.config import ValkeyConfig
    time.sleep(0.2)
    out = Path(os.environ["T1_OUT"]) / f"{os.path.basename(__file__)}-{i}.json"
    out.write_text(json.dumps([os.environ["PYTEST_XDIST_WORKER"], ArcadeDBConfig.from_env(database="ospreyflow").database,
                               ValkeyConfig.from_env().db]))
"""


def test_the_serial_files_run_on_one_worker_on_the_shared_graph_the_rest_spread(tmp_path: Path) -> None:
    """Through xdist itself (`-n 2 --dist loadgroup`), not the hook alone: every serial test on one worker, opening the
    shared `ospreyflow` and Valkey's db 0 in-process as its children and its db-0 clients would; the other file's tests
    each on their worker's own (where xdist sends them is its own choice)."""
    for name in ("test_serial_a.py", "test_serial_b.py", "test_spread.py"):
        (tmp_path / name).write_text(_SERIAL_PLANTED)
    serial = os.pathsep.join(str((tmp_path / n).resolve()) for n in ("test_serial_a.py", "test_serial_b.py"))
    ran, _ = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup",
                  files=("test_serial_a.py", "test_spread.py", "test_serial_b.py"), OSPREY_WORKER_SERIAL_EXTRA=serial)  # fmt: skip
    assert ran.returncode == 0, ran.stdout + ran.stderr
    seen = {p.stem: json.loads(p.read_text()) for p in (tmp_path / "out").glob("test_*.json")}
    serial_seen = [v for k, v in seen.items() if k.startswith("test_serial_")]
    spread_seen = [v for k, v in seen.items() if k.startswith("test_spread")]
    assert len(serial_seen) == 12 and len(spread_seen) == 6, seen
    assert len({w for w, _, _ in serial_seen}) == 1, serial_seen
    assert {db for _, db, _ in serial_seen} == {"ospreyflow"}, serial_seen
    assert {v for _, _, v in serial_seen} == {0}, "a serial test's Valkey database is its db-0 clients' own"
    for worker, db, valkey_db in spread_seen:
        assert db.endswith(f"_{worker}"), spread_seen
        assert valkey_db == int(worker[2:]) + 1, spread_seen


def test_a_child_that_inherits_a_worker_s_environment_is_not_taken_for_a_worker(tmp_path: Path) -> None:
    """A nested pytest (the live proof's own) sees `PYTEST_XDIST_WORKER` from its parent; it must not take the
    parent's names, nor drop them at its end."""
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", PYTEST_XDIST_WORKER="gw3", PYTEST_XDIST_TESTRUNUID="ab" * 16)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert seen["gw3"]["arcadedb"] == "ospreyflow" and seen["gw3"]["valkey"] == 0, seen


def test_more_workers_than_valkey_has_databases_is_refused_before_any_worker_starts(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "16", "--dist", "loadgroup")
    assert ran.returncode != 0 and "at most 15 workers" in ran.stdout + ran.stderr
    assert seen == {}


# --- After both reviews (10 November 2026 evening) -------------------------------------------------------------------


def test_a_run_nested_in_a_worker_takes_the_valkey_databases_after_the_outer_run_s(tmp_path: Path) -> None:
    """The live proof runs `-n 2` inside a worker of an outer `-n N` run: its workers must not take db 1 and db 2,
    the outer gw0's and gw1's, and flush them mid-test. The outer controller exports how many it took."""
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup",
                     OSPREY_WORKER_VALKEY_TAKEN="4")  # fmt: skip
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert {w: n["valkey"] for w, n in seen.items()} == {"gw0": 5, "gw1": 6}, seen
    assert {n["taken"] for n in seen.values()} == {"6"}


def test_a_nested_run_that_would_pass_db_15_is_refused_before_any_worker_starts(tmp_path: Path) -> None:
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup",
                     OSPREY_WORKER_VALKEY_TAKEN="14")  # fmt: skip
    assert ran.returncode != 0 and "the enclosing run took 14" in ran.stdout + ran.stderr
    assert seen == {}


def test_n_auto_takes_as_many_workers_as_valkey_has_databases_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-n auto` on the 16-core server was refused (16 > 15): it is given what fits instead."""
    from tests import worker_isolation

    monkeypatch.setattr(os, "sched_getaffinity", lambda _pid: set(range(16)), raising=False)
    monkeypatch.delenv("OSPREY_WORKER_VALKEY_TAKEN", raising=False)
    assert worker_isolation.pytest_xdist_auto_num_workers(None) == 15  # type: ignore[arg-type]
    monkeypatch.setenv("OSPREY_WORKER_VALKEY_TAKEN", "11")
    assert worker_isolation.pytest_xdist_auto_num_workers(None) == 4  # type: ignore[arg-type]
    # Through xdist itself, at its real call site: 13 taken leaves 2, and `-n auto` runs on them, not refused.
    ran, seen = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "auto", "--dist", "loadgroup",
                     OSPREY_WORKER_VALKEY_TAKEN="13")  # fmt: skip
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(n["valkey"] for n in seen.values()) == [14, 15], seen


def test_the_sweep_takes_only_this_plugin_s_names_from_a_killed_run() -> None:
    """A running run's names (an outer one's, or a second lane's on the same stack) are never stale; nor is
    anything not of this plugin's shape: the shared names, a per-test `conformance_*`, or the old unstamped shape."""
    from tests.worker_isolation import STALE_AFTER, stale

    now = 1_800_000_000
    old, fresh = now - STALE_AFTER - 1, now - 60
    names = [
        f"ospreyflow_x1a2b3c4d_t{old}_gw0", f"ospreyflow-x1a2b3c4d-t{old}-gw3-staging",
        f"ospreyflow_x1a2b3c4d_t{fresh}_gw0", f"ospreyflow-x1a2b3c4d-t{fresh}-gw1-staging",
        "ospreyflow", "ospreyflow-staging", f"conformance_{old}_abc", "ospreyflow_x1a2b3c4d_gw0",
    ]  # fmt: skip
    assert stale(names, now) == [f"ospreyflow_x1a2b3c4d_t{old}_gw0", f"ospreyflow-x1a2b3c4d-t{old}-gw3-staging"]


_STORES_CONFTEST = """
import os
from pathlib import Path

import tests.worker_isolation as w

FAIL = os.environ.get("T1_FAIL", "")


def _note(name):
    who = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    with (Path(os.environ["T1_OUT"]) / f"calls-{who}.txt").open("a") as log:
        log.write(name + "\\n")
    if name == FAIL:
        raise ConnectionError(f"{name} refused (planted)")


def _valkey_take(db, run):
    _note("valkey-made")


def _valkey_flush(db):
    _note("valkey")


def _buckets(prefix):
    _note("buckets" if prefix else "sweep-buckets")
    return []


async def _postgres(admin, create, drop=None, left=False):
    _note("sweep-postgres" if left else "postgres-made" if create else "postgres")
    return []


async def _arcadedb_create(database):
    _note("arcadedb-made")


async def _arcadedb(drop, left=False):
    _note("sweep-arcadedb" if left else "arcadedb")
    return []


def pytest_sessionfinish(session):
    _note("sessionfinish")  # inside xdist's own sessionfinish, before its workerfinished: what follows, no report sees


w._valkey_take, w._valkey_flush, w._buckets = _valkey_take, _valkey_flush, _buckets
w._postgres, w._arcadedb_create, w._arcadedb = _postgres, _arcadedb_create, _arcadedb
"""


def _stores_run(tmp_path: Path, fail: str = "", **extra: Any) -> tuple[subprocess.CompletedProcess[str], dict[str, list[str]]]:
    """The planted file under `-n 2` through xdist itself, its stores stood in for by a conftest that records each
    make and clear, and refuses the one named in `fail` as an unreachable store would (by raising)."""
    (tmp_path / "conftest.py").write_text(_STORES_CONFTEST)
    ran, _ = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup",
                  T1_FAIL=fail, OSPREY_WORKER_STORES="1", **extra)  # fmt: skip
    calls = {p.stem.removeprefix("calls-"): p.read_text().split() for p in (tmp_path / "out").glob("calls-*.txt")}
    return ran, calls


_MADE = ["valkey-made", "postgres-made", "arcadedb-made"]
_CLEARED = ["arcadedb", "postgres", "valkey", "buckets"]
_END = ["sessionfinish"]  # every clear before it: inside the run, where a failure is reported


def test_each_worker_makes_its_stores_at_its_first_test_and_clears_them_at_its_last(tmp_path: Path) -> None:
    ran, calls = _stores_run(tmp_path)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert calls.pop("controller") == ["sweep-arcadedb", "sweep-postgres", "sweep-buckets", *_END], calls
    assert sorted(calls) == ["gw0", "gw1"], calls
    assert all(c == _MADE + _CLEARED + _END for c in calls.values()), calls


def test_a_store_that_fails_to_clear_fails_the_run_and_the_others_are_still_cleared(tmp_path: Path) -> None:
    """The merger's review: cleared in `pytest_unconfigure`, after xdist's `workerfinished`, a failure was ignored
    and the run exited 0. Now it is the last test's teardown error, which the controller counts."""
    ran, calls = _stores_run(tmp_path, fail="arcadedb")
    assert ran.returncode != 0, ran.stdout + ran.stderr
    assert "arcadedb refused (planted)" in ran.stdout + ran.stderr
    assert all(c == _MADE + _CLEARED + _END for w, c in calls.items() if w != "controller"), calls


def test_a_make_that_fails_part_way_fails_the_run_and_what_was_made_is_cleared(tmp_path: Path) -> None:
    ran, calls = _stores_run(tmp_path, fail="arcadedb-made")
    assert ran.returncode != 0, ran.stdout + ran.stderr
    assert "arcadedb-made refused (planted)" in ran.stdout + ran.stderr
    workers = {w: c for w, c in calls.items() if w != "controller"}
    assert workers and all(
        c[:3] == _MADE and set(c[3:-1]) == {"arcadedb", "postgres", "valkey"} and c[-1:] == _END for c in workers.values()
    ), calls


def test_a_nested_run_does_not_sweep(tmp_path: Path) -> None:
    """Its outer run's sweep is the outer run's; a nested one (the live proof's) must not drop what it may not own."""
    ran, calls = _stores_run(tmp_path, OSPREY_WORKER_VALKEY_TAKEN="4")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert calls.get("controller") == _END, calls


def test_a_replacement_worker_past_the_run_s_count_is_refused() -> None:
    """xdist replaces a crashed worker with gw<count + k>: its Valkey database would be outside the run's own (on a
    nested run's, or past db 15)."""
    from tests.worker_isolation import worker_names

    assert worker_names("gw1", "abcdef12", 1_700_000_000, first=1, count=2)["VALKEY_DB"] == "2"
    with pytest.raises(pytest.UsageError, match="past the run's 2 workers"):
        worker_names("gw2", "abcdef12", 1_700_000_000, first=1, count=2)


class _Valkey:
    """Answers as Valkey does: `SET … NX` returns None when the key is there, and leaves it as it was."""

    def __init__(self, held: str | None = None) -> None:
        self.keys: dict[str, bytes] = {} if held is None else {"osprey:worker-isolation:claim": held.encode()}
        self.connection_pool = type("Pool", (), {"connection_kwargs": {"db": 3}})()

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self.keys:
            return None
        self.keys[key] = value.encode()
        return True

    def get(self, key: str) -> bytes | None:
        return self.keys.get(key)


def test_a_valkey_database_another_run_holds_is_refused() -> None:
    from tests.worker_isolation import claim_valkey

    free = _Valkey()
    claim_valkey(free, "run-a")
    assert free.keys == {"osprey:worker-isolation:claim": b"run-a"}
    claim_valkey(free, "run-a")  # its own claim again: a worker's second make
    with pytest.raises(RuntimeError, match="db 3 is held by run run-a"):
        claim_valkey(free, "run-b")
    assert free.keys == {"osprey:worker-isolation:claim": b"run-a"}


def test_stores_are_made_only_where_the_lane_holds_a_lease(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every lane session exports OSPREY_LANE; only a lease (as the port guard reads it) makes a run live."""
    from tests import worker_isolation

    monkeypatch.delenv("OSPREY_WORKER_STORES", raising=False)
    monkeypatch.setenv("OSPREY_LEASE_DIR", str(tmp_path))
    monkeypatch.setenv("OSPREY_LANE", "admin")
    assert worker_isolation._live() is False
    (tmp_path / "stack-b.lease").mkdir()
    (tmp_path / "stack-b.lease" / "info").write_text("holder=studio\nstack=b\n")
    assert worker_isolation._live() is False
    (tmp_path / "stack-b.lease" / "info").write_text("holder=admin\nstack=b\n")
    assert worker_isolation._live() is True


def test_the_run_s_header_names_its_workers_and_databases(tmp_path: Path) -> None:
    ran, _ = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "2", "--dist", "loadgroup", "-v")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "worker_isolation: 2 workers, Valkey databases 1 to 2, no stores made (offline)" in ran.stdout, ran.stdout


def test_a_file_that_starts_containers_is_grouped_and_one_that_fakes_docker_is_not(tmp_path: Path) -> None:
    """The shapes the real files take (10 November 2026: at 8 workers each worker's own module-scoped Keycloak in
    `test_organisation_sign_in.py` "never became ready"): `run -d` with options between (`test_workspace_bundle.py`'s
    `run --rm -d`), the TLS fixtures imported relatively as all four of their users do. A file that only fakes
    `docker`, or names it in a string, is not grouped. Container files join the serial group, so none runs beside a
    serial file tearing down a fixed compose project."""
    from tests.worker_isolation import pytest_collection_modifyitems, starts_containers

    shapes = {
        "test_a.py": 'argv = ["run", "-d", "--name", name, "--network", network]\n',
        "test_b.py": 'subprocess.run(["docker", "compose", "-f", str(f), "up", "-d"])\n',
        "test_c.py": 'subprocess.run([*compose, "up", "--wait"])\n',
        "test_d.py": "assert wait_until_healthy(running)\n",
        "test_e.py": "from .tls_fixtures import docker, render\n",
        "test_h.py": 'started = _docker("run", "--rm", "-d", "--name", name, image)\n',
        "test_f.py": 'def _docker(containers: str = "", volumes: str = ""):\n    return f"docker ps {containers}"\n',
        "test_g.py": 'assert calls[0] == "docker run"\n',
        "test_i.py": "from tests.harness.tls_fixtures import docker\n",
    }
    for name, text in shapes.items():
        (tmp_path / name).write_text(text)
    assert [n for n in shapes if starts_containers(tmp_path / n)] == [
        "test_a.py", "test_b.py", "test_c.py", "test_d.py", "test_e.py", "test_h.py", "test_i.py"
    ]  # fmt: skip

    class _Item:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.marks: list[pytest.MarkDecorator] = []

        def add_marker(self, mark: pytest.MarkDecorator) -> None:
            self.marks.append(mark)

    real = ["organisation_sign_in", "proxy_tls_caddy", "render_memory", "apply_env", "deployment_guard",
            "workspace_bundle", "tls_check"]  # fmt: skip
    items = [_Item(BUILD / f"tests/harness/test_{n}.py") for n in real]
    pytest_collection_modifyitems(None, items)  # type: ignore[arg-type]
    assert {i.path.stem: [m.mark.args for m in i.marks] for i in items} == {
        "test_organisation_sign_in": [("serial",)], "test_proxy_tls_caddy": [("serial",)],
        "test_render_memory": [("serial",)], "test_apply_env": [("serial",)], "test_deployment_guard": [],
        "test_workspace_bundle": [("serial",)], "test_tls_check": [("serial",)],
    }  # fmt: skip


_CONTAINER_PLANTED = """
import json, os, time
from pathlib import Path

import pytest

# argv = ["run", "-d", ...]: the shape that groups this file with the other container files

@pytest.mark.parametrize("i", range(4))
def test_one(i):
    time.sleep(0.2)
    out = Path(os.environ["T1_OUT"]) / f"{os.path.basename(__file__)}-{i}.json"
    out.write_text(json.dumps(os.environ["PYTEST_XDIST_WORKER"]))
"""


def test_the_container_files_run_on_one_worker_with_the_serial_ones_through_xdist(tmp_path: Path) -> None:
    for name in ("test_box_a.py", "test_box_b.py", "test_serial_c.py"):
        (tmp_path / name).write_text(_CONTAINER_PLANTED)
    serial = str((tmp_path / "test_serial_c.py").resolve())
    ran, _ = _run(tmp_path, "-p", "tests.worker_isolation", "-n", "3", "--dist", "loadgroup",
                  files=("test_box_a.py", "test_box_b.py", "test_serial_c.py"), OSPREY_WORKER_SERIAL_EXTRA=serial)  # fmt: skip
    assert ran.returncode == 0, ran.stdout + ran.stderr
    seen = [json.loads(p.read_text()) for p in (tmp_path / "out").glob("test_*.json")]
    assert len(seen) == 12 and len(set(seen)) == 1, seen
