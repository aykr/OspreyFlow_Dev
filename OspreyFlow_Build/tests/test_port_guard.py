"""The test-harness port guard (`tests/port_guard.py`; the owner's answer of 1 November 2026).

Each case runs a **planted** test session in a subprocess, the shape the real incident had: a test
that reads ArcadeDB's address the way `graph_arcadedb/client.py` does (`ArcadeDBConfig.from_env`)
and asks it whether it is ready, in a shell with no `ARCADEDB_HTTP_PORT`. Under the guard sits a
**tripwire**: the planted session's own conftest replaces `socket.socket.connect` before anything
else runs, records every address asked for, and raises instead of connecting. So no case here can
reach the owner's deployment, with the guard or without it — and "the guard refused before any
connection" is checked as "the tripwire recorded nothing".

What a mistake would do, and the case that catches it (rule 12):
- the unpinned run going ahead (the step 5 incident) —
  `test_an_unpinned_run_is_refused_before_any_connection`; shown red with the guard's start-up check
  removed, when the tripwire records 127.0.0.1:2480;
- a live port named in a test's own code rather than the environment —
  `test_a_connection_to_a_live_port_named_in_code_is_refused_before_it_is_made`;
- the guard refusing CI's own service containers (ci.yml's `conformance` job runs ArcadeDB on 2480
  and Postgres on 5432) — `test_ci_true_allows_the_ports_ci_s_own_containers_use`;
- a pinned run refused, so the guard is switched off in anger —
  `test_a_pinned_run_goes_ahead`.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from tests.port_guard import LIVE_PORTS, URL_SETTINGS, live_settings

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"

TRIPWIRE = """
import socket

ASKED = []
_real_connect = socket.socket.connect


def _tripwire(self, address):
    ASKED.append(address)
    print(f"TRIPWIRE: a connection to {address!r} was asked for", flush=True)
    raise RuntimeError(f"tripwire: never connects ({address!r})")


socket.socket.connect = _tripwire
socket.socket.connect_ex = _tripwire
"""

UNPINNED = """
import httpx
from adapters.graph_arcadedb.client import ArcadeDBConfig


def test_arcadedb_is_ready():
    config = ArcadeDBConfig.from_env("ospreyflow")
    httpx.get(f"{config.base_url}/api/v1/ready", timeout=2)
"""

NAMED_IN_CODE = """
import socket

import pytest

from tests.port_guard import LivePortRefused
import conftest


def test_the_glass_on_8080():
    with pytest.raises(LivePortRefused, match="8080"):
        socket.create_connection(("127.0.0.1", 8080), timeout=2)
    assert conftest.ASKED == [], "the guard must refuse before the tripwire is asked"
"""


def _run(tmp_path: Path, test_source: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    (tmp_path / "conftest.py").write_text(TRIPWIRE, encoding="utf-8")
    (tmp_path / "test_planted.py").write_text(test_source, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    environ = {
        k: v
        for k, v in os.environ.items()
        if k not in {"CI", "PYTEST_ADDOPTS", *URL_SETTINGS}
        and not k.endswith("_PORT")
        and not k.endswith("_HOST")
    }
    environ["PYTHONPATH"] = os.pathsep.join(
        [str(BUILD), str(CORE), str(CORE / "packages"), str(tmp_path)]
    )
    environ.update(env)
    return subprocess.run(  # noqa: S603 - this interpreter, a fixed argument list
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.port_guard",
            str(tmp_path),
        ],  # fmt: skip
        cwd=tmp_path,
        env=environ,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_an_unpinned_run_is_refused_before_any_connection(tmp_path: Path) -> None:
    run = _run(tmp_path, UNPINNED, {})
    said = run.stdout + run.stderr
    assert "TRIPWIRE" not in said, f"a connection was asked for before the guard refused:\n{said}"
    assert run.returncode == 4, f"expected a usage error (4), got {run.returncode}:\n{said}"
    assert "would reach a live deployment" in said
    assert "ARCADEDB_HTTP_PORT is not set, so it is 2480" in said
    assert "ArcadeDB (the owner's deployment)" in said
    assert "ARCADEDB_HTTP_PORT=2491" in said, "the refusal says how to pin the ports"


def test_a_connection_to_a_live_port_named_in_code_is_refused_before_it_is_made(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, NAMED_IN_CODE, {"ARCADEDB_HTTP_PORT": "2491"})
    said = run.stdout + run.stderr
    assert run.returncode == 0, said
    assert "TRIPWIRE" not in said


def test_ci_true_allows_the_ports_ci_s_own_containers_use(tmp_path: Path) -> None:
    run = _run(tmp_path, UNPINNED, {"CI": "true", "ARCADEDB_HTTP_PORT": "2480"})
    said = run.stdout + run.stderr
    assert "would reach a live deployment" not in said
    # The guard stood aside, so the planted test went on to ask for 2480 — caught by the tripwire,
    # never connected.
    assert "TRIPWIRE: a connection to" in said and "2480" in said, said
    assert "port guard: CI=true" in said


def test_a_pinned_run_goes_ahead(tmp_path: Path) -> None:
    run = _run(tmp_path, UNPINNED, {"ARCADEDB_HTTP_PORT": "2491"})
    said = run.stdout + run.stderr
    assert "would reach a live deployment" not in said
    assert "port guard: on" in said
    # It went ahead and asked for 2491, the pinned port (the tripwire stops it there too).
    assert "2491" in said


def test_every_live_port_set_in_the_environment_is_named() -> None:
    found = live_settings(
        {
            "ARCADEDB_HTTP_PORT": "2491",
            "POSTGRES_PORT": "5432",
            "OSPREY_WORKSPACE_ORIGIN": "http://localhost:8080",
            "OSPREY_KEYCLOAK_ORIGIN": "http://127.0.0.1:8081",
            "OSPREY_OLLAMA_URL": "http://localhost",
        }
    )
    assert [line.split(":")[0].split("=")[0] for line in found] == [
        "POSTGRES_PORT",
        "OSPREY_WORKSPACE_ORIGIN",
        "OSPREY_KEYCLOAK_ORIGIN",
        "OSPREY_OLLAMA_URL",
    ]
    assert set(LIVE_PORTS) == {2480, 5432, 80, 8080, 8081}


def test_a_remote_host_on_the_same_port_is_not_this_machine() -> None:
    remote = {"ARCADEDB_HTTP_PORT": "2480", "ARCADEDB_HOST": "arcadedb.ci.internal"}
    assert live_settings(remote) == []


import pytest  # noqa: E402  (the file above is a planted test text, not this module's imports)


class _RecordingSocket:
    """Stands in for `socket.socket`: records what it was asked to connect to and never connects."""

    asked: list[object] = []

    def connect(self, address: object) -> None:
        type(self).asked.append(address)

    def connect_ex(self, address: object) -> int:
        type(self).asked.append(address)
        return 0


def _hold_lease(lease_dir: Path, holder: str) -> None:
    (lease_dir / "stack.lease").mkdir(parents=True)
    (lease_dir / "stack.lease" / "info").write_text(f"holder={holder}\npurpose=x\nsince=x\nworktree=x\n")


@pytest.mark.parametrize(
    ("holder", "lane", "allowed"),
    [(None, "case", False), ("studio", "case", False), ("studio", None, False), ("case", "case", True)],
)
def test_the_leased_stack_is_reached_only_by_the_lane_holding_the_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, holder: str | None, lane: str | None, allowed: bool
) -> None:
    """ADR-142 decision 4 and rule 14, made mechanical: a connection to the throwaway stack's ports on
    this machine goes ahead only for the lane named in the lease. Refused, it is a connection error,
    so a test sees the stack as absent and skips, exactly as when the stack is down."""
    from tests import port_guard

    monkeypatch.setenv("OSPREY_LEASE_DIR", str(tmp_path))
    if lane is None:
        monkeypatch.delenv("OSPREY_LANE", raising=False)
    else:
        monkeypatch.setenv("OSPREY_LANE", lane)
    if holder is not None:
        _hold_lease(tmp_path, holder)
    _RecordingSocket.asked = []
    restore = port_guard.guard_socket(_RecordingSocket)  # type: ignore[arg-type]
    try:
        for port in (2491, 55433, 6379):
            if allowed:
                _RecordingSocket().connect(("127.0.0.1", port))
            else:
                with pytest.raises(ConnectionRefusedError, match="lease"):
                    _RecordingSocket().connect(("127.0.0.1", port))
    finally:
        restore()
    assert len(_RecordingSocket.asked) == (3 if allowed else 0)


# --- The guard reaches the Python processes a test starts (found 7 November 2026, 21:39Z) ------------
#
# A stopped full-suite run of the case lane left `test_statelessness.py`'s second Conduit (a
# `python -m uvicorn` child, its parent gone) holding 35 connections to the leased stack during the
# studio lane's lease: the guard wrapped this process's sockets only, so a child process, and uvloop's
# own connections (libuv, not `socket.socket.connect`), went round it.


def _listener() -> tuple[socket.socket, int]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    srv.settimeout(0.5)
    return srv, srv.getsockname()[1]


def _accepted(srv: socket.socket) -> bool:
    try:
        conn, _ = srv.accept()
    except TimeoutError:
        return False
    conn.close()
    return True


_CHILD_PLAIN = (
    "import socket, sys\n"
    "s = socket.socket()\n"
    "try:\n"
    "    s.connect(('127.0.0.1', int(sys.argv[1])))\n"
    "    print('CONNECTED')\n"
    "except ConnectionRefusedError as e:\n"
    "    print('REFUSED', type(e).__name__)\n"
)
_CHILD_UVLOOP = (
    "import asyncio, sys, uvloop\n"
    "async def main():\n"
    "    try:\n"
    "        r, w = await asyncio.open_connection('127.0.0.1', int(sys.argv[1]))\n"
    "        print('CONNECTED'); w.close()\n"
    "    except ConnectionRefusedError as e:\n"
    "        print('REFUSED', type(e).__name__)\n"
    "uvloop.run(main())\n"
)


@pytest.mark.skipif(os.environ.get("CI", "").lower() == "true", reason="CI=true: the guard stands aside")
@pytest.mark.parametrize("child", [_CHILD_PLAIN, _CHILD_UVLOOP], ids=["plain-socket", "uvloop"])
def test_a_process_a_test_starts_is_refused_the_leased_stack_too(tmp_path: Path, child: str) -> None:
    """The child is started as a test starts one, with this run's own environment (`{**os.environ}`);
    the leased port is a real listener here, named leased through the guard's test seam, so a
    connection that got through would be seen arriving."""
    pytest.importorskip("uvloop") if "uvloop" in child else None
    srv, port = _listener()
    _hold_lease(tmp_path, "studio")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path), "OSPREY_LANE": "case",
           "OSPREY_GUARD_TEST_PORTS": str(port)}
    try:
        out = subprocess.run([sys.executable, "-c", child, str(port)], env=env,
                             capture_output=True, text=True, timeout=30)
        arrived = _accepted(srv)
    finally:
        srv.close()
    assert "REFUSED LeaseNotHeld" in out.stdout, out.stdout + out.stderr
    assert not arrived
