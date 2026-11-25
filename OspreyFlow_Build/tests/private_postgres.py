"""A private, throwaway PostgreSQL for a test (slice AD1d; the owner's ruling (c), 25 November 2026).

**Why this exists.** A test that needs a real PostgreSQL but no shared one starts its own: `initdb` and
`pg_ctl` in a temporary folder, removed at the end. `tools/test_file_coverage_check.py` reads a test
file's `import` statements, and a file that imports `asyncpg` **and** this module (`tests.private_postgres`)
and nothing else live is not a live-service test: it is not listed in the `test` job's ignore list nor in
a live-service job. No import is ever written to miss that check; this module is the one real way.

**What it does.** `running_postgres(folder)` finds `initdb` (the machine's own PostgreSQL: on `PATH`, then
Homebrew's `postgresql@*` and Debian's `/usr/lib/postgresql/*/bin`, newest first), makes a data folder
under `folder`, starts the server on a loopback port that `tests/port_guard.py` does not reserve
(never a live deployment's port, nor any lane stack's, nor a closed one), yields its address, and stops
the server and removes everything it made, whatever the test did.

**Where it cannot run** it skips, in words: with no `initdb` on the machine, or as root (PostgreSQL's
`initdb` refuses to run as root).

**What it never touches:** the owner's deployment, the demo, the dev stack or any store port a lane holds.
It listens on a Unix-socket-less loopback port of its own, with trust authentication, in a folder that
disappears; nothing in it is real data.
"""

from __future__ import annotations

import contextlib
import glob
import os
import shutil
import signal
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests import port_guard

#: Where a machine's own PostgreSQL keeps its programs when they are not on `PATH` (Homebrew on Apple
#: silicon and on Intel, Debian and Ubuntu). A module setting so the helper's own test can empty it.
BIN_DIR_GLOBS: tuple[str, ...] = (
    "/opt/homebrew/opt/postgresql@*/bin",
    "/usr/local/opt/postgresql@*/bin",
    "/usr/lib/postgresql/*/bin",
)

USER = "postgres"
DATABASE = "postgres"
HOST = "127.0.0.1"
_START_SECONDS = 60
_PORT_TRIES = 5


@dataclass(frozen=True)
class PrivatePostgres:
    """The address of a running private database, and where it lives."""

    host: str
    port: int
    user: str
    database: str
    folder: Path
    data_dir: Path

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.database}"


def _version_key(directory: str) -> tuple[int, ...]:
    tail = directory.split("postgresql")[-1]
    digits = "".join(c if c.isdigit() else " " for c in tail)
    return tuple(int(part) for part in digits.split())


def bin_dirs() -> list[Path]:
    """Every folder with an `initdb`: `PATH` first, then the machine's own PostgreSQL, newest first."""
    found: list[Path] = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and (Path(entry) / "initdb").is_file():
            found.append(Path(entry))
    for pattern in BIN_DIR_GLOBS:
        for entry in sorted(glob.glob(pattern), key=_version_key, reverse=True):
            if (Path(entry) / "initdb").is_file():
                found.append(Path(entry))
    return found


def _free_port() -> int:
    """A loopback port nothing listens on and the port guard does not reserve."""
    reserved = port_guard.reserved_ports() | set(port_guard.LIVE_PORTS)
    held: list[socket.socket] = []
    try:
        for _ in range(64):
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.bind((HOST, 0))
            port = int(probe.getsockname()[1])
            if port in reserved:
                held.append(probe)  # kept open so the system does not hand it back
                continue
            probe.close()
            return port
        raise RuntimeError("no loopback port outside the guard's reserved ones in 64 tries")
    finally:
        for probe in held:
            probe.close()


def _run(program: Path, *args: str, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - a fixed program from the machine's own PostgreSQL
        [str(program), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "LC_ALL": "C", "PGSSLMODE": "disable"},
    )


def _pid(data_dir: Path) -> int | None:
    try:
        return int((data_dir / "postmaster.pid").read_text(encoding="utf-8").splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None


def _stop(pg_ctl: Path, data_dir: Path) -> None:
    """Stops the server whatever state it is in: `pg_ctl`'s stop, then the process itself if that failed."""
    if _pid(data_dir) is None:
        return
    with contextlib.suppress(Exception):
        _run(pg_ctl, "-D", str(data_dir), "-m", "immediate", "-w", "-t", "30", "stop", timeout=60)
    pid = _pid(data_dir)
    if pid is None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(pid, signal.SIGKILL)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.1)


@contextlib.contextmanager
def running_postgres(folder: Path) -> Iterator[PrivatePostgres]:
    """A private PostgreSQL under `folder` for the `with` block; everything it made is gone after.

    Skips the test, saying why, where there is no `initdb` or the process is root.
    """
    if os.geteuid() == 0:
        pytest.skip("initdb refuses to run as root, so a private PostgreSQL cannot start here")
    dirs = bin_dirs()
    if not dirs:
        pytest.skip(
            "no initdb on this machine (not on PATH, nor in Homebrew's postgresql@* nor "
            "/usr/lib/postgresql/*/bin): install PostgreSQL to run this test"
        )
    pg_ctl = next((d / "pg_ctl" for d in dirs if (d / "pg_ctl").is_file()), None)
    if pg_ctl is None:
        pytest.skip(f"initdb was found in {dirs[0]} but pg_ctl was not: an incomplete install")
    initdb = dirs[0] / "initdb"

    work = folder / "private_postgres"
    data_dir = work / "data"
    # Made before the `try`: if the folder is already there, something else owns it (another instance
    # running in it, say) and this call refuses without stopping or removing anything.
    work.mkdir(parents=True, exist_ok=False)
    started = False
    try:
        made = _run(
            initdb,
            "-D", str(data_dir),
            "-U", USER,
            "--auth=trust",
            "-E", "UTF8",
            "--no-locale",
            timeout=120,
        )  # fmt: skip
        if made.returncode != 0:
            raise RuntimeError(f"initdb failed: {made.stderr.strip() or made.stdout.strip()}")
        log = work / "server.log"
        last = ""
        for _ in range(_PORT_TRIES):
            port = _free_port()
            with (data_dir / "postgresql.conf").open("a", encoding="utf-8") as conf:
                conf.write(
                    f"\nlisten_addresses = '{HOST}'\nport = {port}\nunix_socket_directories = ''\n"
                    "fsync = off\nsynchronous_commit = off\nfull_page_writes = off\n"
                )
            result = _run(
                pg_ctl, "-D", str(data_dir), "-l", str(log), "-w", "-t", str(_START_SECONDS), "start",
                timeout=_START_SECONDS + 30,
            )  # fmt: skip
            if result.returncode == 0:
                started = True
                break
            last = result.stderr.strip() or result.stdout.strip()
            _stop(pg_ctl, data_dir)
        if not started:
            tail = log.read_text(encoding="utf-8")[-800:] if log.is_file() else ""
            raise RuntimeError(f"the private PostgreSQL did not start: {last} {tail}")
        yield PrivatePostgres(HOST, port, USER, DATABASE, work, data_dir)
    finally:
        _stop(pg_ctl, data_dir)
        shutil.rmtree(work, ignore_errors=True)
