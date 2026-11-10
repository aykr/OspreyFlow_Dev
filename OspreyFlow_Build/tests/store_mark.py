"""`pytest.mark.store`, enforced at the connection (admin's T1 part 2, 10 November 2026).

**Why.** What is live has been a file list (the Makefile's `--ignore`s, `ci.yml`'s live jobs). `test-file-coverage-check`
guessed it from the names a file imports, which is wrong both ways: an offline `httpx.MockTransport` test that imports
the client class read as live, and a test reaching a store through a fixture, importing no such name, read as offline.
This module answers from what a test does.

**What it does.** It wraps `socket.socket.connect` and `connect_ex`, as `tests/port_guard.py` does for the owner's live
ports; it is installed after that guard, and adds no refusal of its own. While a test runs (its setup, call and
teardown), a connection to a **store's port** is recorded against that test unless the test is marked `store`. The
store ports are the ones this run's settings give ArcadeDB, Postgres, Valkey and ClickHouse, or, for a setting not
set, the code's own default (`tests/port_guard.py`'s `PORT_SETTINGS`): so CI's offline job, which pins no port, is
watched too. An offline run's closed ports (59991 to 59994) count: an unmarked test that tries to reach them needs a
store, whether or not one answers.

**What it cannot see**, each a limit to know before fail mode is on:
- **the object store**: every client here is pyarrow's C++ `S3FileSystem`, which opens its sockets below
  `socket.socket.connect` (as `tests/port_guard.py` notes); a test that reaches it alone is not seen, so the mark
  commit marks the live files whatever the guard reports;
- **a child process** (a `python -m scripts.*` seed, a uvicorn Conduit): the guard is in this process only;
- **uvloop**, which `port_guard` neutralises outside CI only;
- **a pooled connection reused** by a later test, which makes no new connection;
- **a connection made between tests** (collection, a leftover task) is not recorded, and one a background thread
  makes during another test is recorded against that test.

**Two modes**, chosen by `OSPREY_STORE_MARK`:
- `report` (the default until the marks land): nothing fails. The session ends with every unmarked test that reached a
  store, by store, and writes them to `$OSPREY_STORE_MARK_REPORT` if that is set.
- `fail`: each such test's report is turned failed after it runs, naming the store and the port. This happens at the
  report, not by raising inside the connection, so a client that catches every error cannot hide it.

The guard's own red-then-green proof (rule 15) is `tests/test_store_mark.py`.
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Generator, Mapping
from typing import Any
import pytest

from tests.port_guard import PORT_SETTINGS

#: Each setting naming a store's port, and the store (the defaults are `port_guard.PORT_SETTINGS`'s).
STORES: dict[str, str] = {
    "ARCADEDB_HTTP_PORT": "ArcadeDB",
    "POSTGRES_PORT": "Postgres",
    "VALKEY_PORT": "Valkey",
    "CLICKHOUSE_HTTP_PORT": "ClickHouse",
}


def store_ports(environ: Mapping[str, str]) -> dict[int, str]:
    """The ports this run gives the stores, set or the code's default: port -> the store's name."""
    ports: dict[int, str] = {}
    for setting, store in STORES.items():
        value = environ.get(setting) or PORT_SETTINGS[setting]
        if value.isdigit():
            ports[int(value)] = store
    return ports


def mode(environ: Mapping[str, str]) -> str:
    value = environ.get("OSPREY_STORE_MARK", "report")
    if value not in ("report", "fail"):
        raise pytest.UsageError(f"OSPREY_STORE_MARK must be report or fail, not {value!r}")
    return value


class _Watch:
    """The test running now, and what each unmarked test reached."""

    def __init__(self, ports: dict[int, str]) -> None:
        self.ports = ports
        self.current: pytest.Item | None = None
        self.marked = False
        self.reached: dict[str, set[str]] = {}

    def note(self, address: Any) -> None:
        if self.current is None or self.marked:
            return
        if isinstance(address, tuple) and len(address) >= 2 and address[1] in self.ports:
            what = f"{self.ports[address[1]]} on port {address[1]}"
            self.reached.setdefault(self.current.nodeid, set()).add(what)


def watch_socket(watch: _Watch, sock_cls: type[socket.socket] = socket.socket) -> Callable[[], None]:
    original_connect = sock_cls.connect
    original_connect_ex = sock_cls.connect_ex

    def connect(self: socket.socket, address: Any) -> None:
        watch.note(address)
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        watch.note(address)
        return original_connect_ex(self, address)

    sock_cls.connect = connect  # type: ignore[method-assign]
    sock_cls.connect_ex = connect_ex  # type: ignore[method-assign]

    def restore() -> None:
        sock_cls.connect = original_connect  # type: ignore[method-assign]
        sock_cls.connect_ex = original_connect_ex  # type: ignore[method-assign]

    return restore


_KEY = pytest.StashKey[_Watch]()


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "store: needs a real store (ArcadeDB, Postgres, Valkey, ClickHouse, or the object store); "
        "an unmarked test that reaches one is reported (tests/store_mark.py)",
    )
    mode(os.environ)  # a bad value stops the run before anything is collected
    watch = _Watch(store_ports(os.environ))
    config.stash[_KEY] = watch
    config.add_cleanup(watch_socket(watch))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None]:
    watch = item.config.stash.get(_KEY, None)
    if watch is not None:
        watch.current, watch.marked = item, item.get_closest_marker("store") is not None
    yield
    if watch is not None:
        watch.current = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[Any]:
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    watch = item.config.stash.get(_KEY, None)
    if watch is None or report.when != "teardown" or mode(os.environ) != "fail":
        return
    reached = watch.reached.get(item.nodeid)
    if reached:
        report.outcome = "failed"
        earlier = f"{report.longrepr}\n\n" if report.longrepr else ""  # a real teardown error is kept
        report.longrepr = earlier + (
            f"UnmarkedStoreTest: {item.nodeid} reached {', '.join(sorted(reached))} and is not marked "
            "store. Mark it (pytestmark = pytest.mark.store, or @pytest.mark.store) so live runs carry "
            "it and make test leaves it out (tests/store_mark.py)."
        )


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    watch = config.stash.get(_KEY, None)
    if watch is None:
        return
    out = os.environ.get("OSPREY_STORE_MARK_REPORT")
    if out:  # written every run, so a clean run never leaves the last run's list behind
        with open(out, "w", encoding="utf-8") as f:
            json.dump({k: sorted(v) for k, v in sorted(watch.reached.items())}, f, indent=1)
    if watch.reached and mode(os.environ) == "report":
        terminalreporter.write_sep("-", f"{len(watch.reached)} unmarked test(s) reached a store")
        shown = sorted(watch.reached.items())[:20]
        for nodeid, reached in shown:
            terminalreporter.write_line(f"{nodeid}: {', '.join(sorted(reached))}")
        if len(watch.reached) > len(shown):
            terminalreporter.write_line(
                f"… and {len(watch.reached) - len(shown)} more"
                + (f" (all in {out})" if out else " (set OSPREY_STORE_MARK_REPORT for the whole list)")
            )
