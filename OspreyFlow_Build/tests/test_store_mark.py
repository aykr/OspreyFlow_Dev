"""`tests/store_mark.py`, `pytest.mark.store` enforced at the connection (admin's T1 part 2, 10 November 2026).

Each case runs a planted test file through pytest in a subprocess, with this repository's plugin and the closed
offline ports (59991 to 59994), in the shapes a live test takes at its real call site: an `arcadedb_adapter` open,
`asyncpg.connect`, a Valkey client's ping, and one client that swallows every error. Red if an unmarked test that
reaches a store goes unreported (or, in `fail` mode, passes), if a marked one is reported, or if a connection to a
port that is not a store's is counted.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1]

_PLANTED = '''
import asyncio, socket
import pytest

def _arcadedb():
    from adapters.graph_arcadedb.testing import arcadedb_adapter
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology
    async def go():
        async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()):
            pass
    asyncio.run(go())

def _postgres():
    import asyncpg
    asyncio.run(asyncpg.connect(host="127.0.0.1", port=59992, user="x", password="x", database="x", timeout=2))

def _valkey():
    import valkey
    valkey.Valkey(host="127.0.0.1", port=59993, socket_connect_timeout=2).ping()

def test_unmarked_arcadedb():
    with pytest.raises(Exception):
        _arcadedb()

def test_unmarked_postgres():
    with pytest.raises(Exception):
        _postgres()

def test_unmarked_valkey():
    with pytest.raises(Exception):
        _valkey()

def test_unmarked_and_swallowed():
    try:
        _arcadedb()
    except BaseException:
        pass  # a client that hides every error: the report still sees the connection

@pytest.mark.store
def test_marked():
    with pytest.raises(Exception):
        _arcadedb()

def test_reaches_a_port_that_is_no_store_s(listener_port):
    s = socket.create_connection(("127.0.0.1", listener_port))
    s.close()

def test_needs_nothing():
    assert True

@pytest.fixture
def listener_port():
    import os
    return int(os.environ["T1_LISTENER"])
'''

UNMARKED = ["test_unmarked_arcadedb", "test_unmarked_postgres", "test_unmarked_valkey", "test_unmarked_and_swallowed"]


@pytest.fixture(scope="module")
def listener() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    threading.Thread(target=lambda: [sock.accept() for _ in range(64)], daemon=True).start()
    return sock.getsockname()[1]


def _run(tmp_path: Path, listener: int, **env: str) -> tuple[subprocess.CompletedProcess[str], dict[str, list[str]]]:
    (tmp_path / "test_planted.py").write_text(_PLANTED)
    report = tmp_path / "report.json"
    environ = {
        **{k: v for k, v in os.environ.items() if k not in ("OSPREY_LANE", "PYTEST_ADDOPTS", "OSPREY_STORE_MARK")},
        "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
        "CLICKHOUSE_HTTP_PORT": "59994", "OSPREY_STORE_MARK_REPORT": str(report), "T1_LISTENER": str(listener),
        "PYTHONPATH": os.pathsep.join(
            [str(BUILD), str(BUILD.parent / "OspreyFlow_Core"), str(BUILD.parent / "OspreyFlow_Core" / "packages")]
        ),
        **env,
    }  # fmt: skip
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rA", "-p", "tests.store_mark", "-p", "no:cacheprovider",
         "-c", os.devnull, "--rootdir", str(tmp_path), str(tmp_path / "test_planted.py")],
        cwd=tmp_path, env=environ, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    reached = json.loads(report.read_text()) if report.exists() else {}
    return ran, {k.split("::")[-1]: v for k, v in reached.items()}


def test_report_mode_names_every_unmarked_store_test_and_fails_nothing(tmp_path: Path, listener: int) -> None:
    ran, reached = _run(tmp_path, listener)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert sorted(reached) == sorted(UNMARKED), (reached, ran.stdout)
    assert reached["test_unmarked_arcadedb"] == ["ArcadeDB on port 59991"]
    assert reached["test_unmarked_postgres"] == ["Postgres on port 59992"]
    assert reached["test_unmarked_valkey"] == ["Valkey on port 59993"]
    assert "4 unmarked test(s) reached a store" in ran.stdout


def test_fail_mode_fails_each_unmarked_store_test_even_one_that_swallows_the_error(
    tmp_path: Path, listener: int
) -> None:
    ran, _ = _run(tmp_path, listener, OSPREY_STORE_MARK="fail")
    assert ran.returncode == 1, ran.stdout
    failed = {l.split("::")[-1].split()[0] for l in ran.stdout.splitlines() if l.startswith("ERROR ") or l.startswith("FAILED ")}
    assert failed == set(UNMARKED), ran.stdout
    assert "UnmarkedStoreTest" in ran.stdout and "is not marked store" in ran.stdout
    for fine in ("test_marked", "test_reaches_a_port_that_is_no_store_s", "test_needs_nothing"):
        assert f"PASSED test_planted.py::{fine}" in ran.stdout, ran.stdout


def test_a_bad_mode_stops_the_run(tmp_path: Path, listener: int) -> None:
    ran, _ = _run(tmp_path, listener, OSPREY_STORE_MARK="maybe")
    assert ran.returncode != 0 and "OSPREY_STORE_MARK must be report or fail" in ran.stdout + ran.stderr


def test_the_store_ports_are_the_run_s_settings_and_the_object_store_s() -> None:
    from tests.store_mark import store_ports

    ports = store_ports({"ARCADEDB_HTTP_PORT": "2492", "POSTGRES_PORT": "55434", "MINIO_ENDPOINT": "localhost:9002"})
    assert ports == {2492: "ArcadeDB", 55434: "Postgres", 9002: "the object store"}


def test_the_suite_s_own_conftest_loads_it(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.pluginmanager.has_plugin("tests.store_mark")
    assert any(m.startswith("store:") for m in pytestconfig.getini("markers"))
