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
            "ANALYTICS_DB_PATH", "MINIO_BUCKET")  # fmt: skip
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
        assert re.fullmatch(rf"ospreyflow_x[0-9a-f]{{8}}_{worker}", names["arcadedb"]), names
        assert names["valkey"] == int(worker[2:]) + 1 and names["valkey"] != 0
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

    assert worker_names("gw14", "abcdef12")["VALKEY_DB"] == "15"
    with pytest.raises(pytest.UsageError, match="at most 15 workers"):
        worker_names("gw15", "abcdef12")


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


#: What only a separate process would reach: the shapes `SERIAL` exists for, besides Valkey's db 0.
_CHILD = re.compile(r"services\.api\.app:app|scripts\.seed_pid\b|\"-m\",\s*\"pytest\"")


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
        if None in keywords:  # **kwargs
            continue
        db = keywords.get("db")
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
    }
    for rel, text in shapes.items():
        (tmp_path / rel).write_text(text)
    assert unserialised(list(shapes)) == [
        "tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_f.py", "tests/test_g.py", "tests/test_j.py"
    ]  # fmt: skip


_SERIAL_PLANTED = """
import json, os, time
from pathlib import Path

import pytest

@pytest.mark.parametrize("i", range(6))
def test_one(i):
    from adapters.graph_arcadedb.client import ArcadeDBConfig
    time.sleep(0.2)
    out = Path(os.environ["T1_OUT"]) / f"{os.path.basename(__file__)}-{i}.json"
    out.write_text(json.dumps([os.environ["PYTEST_XDIST_WORKER"], ArcadeDBConfig.from_env(database="ospreyflow").database]))
"""


def test_the_serial_files_run_on_one_worker_on_the_shared_graph_the_rest_spread(tmp_path: Path) -> None:
    """Through xdist itself (`-n 2 --dist loadgroup`), not the hook alone: every serial test on one worker, opening the
    shared `ospreyflow` in-process as its children would; the other file's tests each on their worker's own (where
    xdist sends them is its own choice)."""
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
    assert len({w for w, _ in serial_seen}) == 1, serial_seen
    assert {db for _, db in serial_seen} == {"ospreyflow"}, serial_seen
    for worker, db in spread_seen:
        assert db.endswith(f"_{worker}"), spread_seen


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
