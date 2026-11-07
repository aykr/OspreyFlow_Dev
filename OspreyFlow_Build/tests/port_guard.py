"""The test-harness port guard (the owner's answer of 1 November 2026, question 8;
`process/BUILD_ORDER_2026-11.md` step 7b; open question 8 there records why).

**Why.** The owner's own deployments listen on this machine: ArcadeDB on 2480, Postgres on 5432, the
proxy on 80, and the Glass and Keycloak on 8080 and 8081. A test run whose shell had not pinned the
store ports reached the everyday deployment's ArcadeDB on 2480 (step 5): `ARCADEDB_HTTP_PORT`
defaults to 2480 in `graph_arcadedb/client.py`. It was refused only because the credentials were
wrong. Nothing in the harness stopped it.

**What it does, in two layers, both before any connection is made:**

1. **At start-up** (`pytest_configure`, before a single test is collected) it reads the port every
   store setting resolves to — the variable if it is set, otherwise the code's own default — and
   every service address a test is pointed at by the environment. If any of them is one of the live
   ports on this machine, the run stops with a usage error that names the setting, the port, whose
   it is, and how to pin it. An unpinned run (no `ARCADEDB_HTTP_PORT`) is refused here.
2. **At every connection** (a wrapper round `socket.socket.connect` and `connect_ex`) a connection
   to a live port on this machine (a loopback address) is refused with `LivePortRefused` before the
   operating system is asked to connect. This catches a test that names a live port in its own code
   rather than through the environment. `LivePortRefused` is deliberately not an `OSError`, so no
   client's "store unavailable" handling turns the refusal into a quiet skip.

**CI.** GitHub Actions' `conformance` job (`.github/workflows/ci.yml`) runs its own service
containers on 2480 (ArcadeDB) and 5432 (Postgres) on a fresh runner where no deployment exists,
and sets those ports explicitly. GitHub sets `CI=true` on every job, so with `CI=true` both layers
stand aside, and the run's header says so. Nowhere else is a live port allowed; there is no
other switch.

The guard's own red-then-green proof (`CLAUDE.md` rule 15) is
`tests/test_port_guard.py`: an unpinned run, planted in a subprocess with a tripwire under the guard
so that nothing can reach 2480, is refused at start-up; without the guard the tripwire records the
attempt on 127.0.0.1:2480.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any
from urllib.parse import urlsplit

import pytest

#: The owner's live ports on this machine, and whose each one is.
LIVE_PORTS: dict[int, str] = {
    2480: "ArcadeDB (the owner's deployment)",
    5432: "Postgres (the owner's deployment)",
    80: "the deployment's proxy",
    8080: "the Glass (the owner's deployment)",
    8081: "Keycloak (the owner's deployment)",
}

#: Each setting that chooses a store's port, with the default the code uses when it is not set
#: (`graph_arcadedb/client.py`, `services/api/config.py`, `analytics_clickhouse`, the gateway).
PORT_SETTINGS: dict[str, str] = {
    "ARCADEDB_HTTP_PORT": "2480",
    "POSTGRES_PORT": "5433",
    "VALKEY_PORT": "6379",
    "CLICKHOUSE_HTTP_PORT": "8123",
    "LITELLM_PORT": "4000",
}
#: The host each port setting is paired with; a remote host is not this machine's deployment.
_HOST_OF = {
    "ARCADEDB_HTTP_PORT": "ARCADEDB_HOST",
    "POSTGRES_PORT": "POSTGRES_HOST",
    "VALKEY_PORT": "VALKEY_HOST",
    "CLICKHOUSE_HTTP_PORT": "CLICKHOUSE_HOST",
    "LITELLM_PORT": "LITELLM_HOST",
}
#: Each setting that points a test at a service by its address.
URL_SETTINGS: tuple[str, ...] = (
    "OSPREY_WORKSPACE_ORIGIN",
    "OSPREY_KEYCLOAK_ORIGIN",
    "OSPREY_TEST_KEYCLOAK_URL",
    "OIDC_JWKS_URL",
    "OIDC_TOKEN_EXCHANGE_URL",
    "OIDC_ADMIN_USERS_URL",
    "OSPREY_OLLAMA_URL",
    "OSPREY_RECOGNISER_URL",
)

PINNED = (
    "ARCADEDB_HTTP_PORT=2491 POSTGRES_PORT=55433 POSTGRES_PASSWORD=throwaway VALKEY_PORT=6379 "
    "CLICKHOUSE_HTTP_PORT=18123"
)


#: The leased throwaway test stack's ports (ADR-142 decision 4; SESSIONS_RUNBOOK.md §4). A test reaches
#: them only from the lane named in the lease, given as OSPREY_LANE: three rule-14 breaches on
#: 7 November 2026 came from tests a lane believed were stack-free.
LEASED_PORTS: dict[int, str] = {
    2491: "ArcadeDB (the leased test stack)",
    55433: "Postgres (the leased test stack)",
    6379: "Valkey (the leased test stack)",
    18123: "ClickHouse (the leased test stack's throwaway, as statelessness-clickhouse starts it)",
}


def _leased_ports() -> dict[int, str]:
    """LEASED_PORTS, plus any port the guard's own tests name in OSPREY_GUARD_TEST_PORTS (a real
    listener of theirs, so a connection that got through is seen arriving). Nothing else sets it."""
    ports = dict(LEASED_PORTS)
    for raw in os.environ.get("OSPREY_GUARD_TEST_PORTS", "").split(","):
        if raw.strip().isdigit():
            ports[int(raw)] = "a port the port guard's own test planted as leased"
    return ports


_SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "port_guard_site")
_BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def propagate(environ: MutableMapping[str, str]) -> None:
    """Hands the guard to every Python process this run starts: `sitecustomize` in
    `tests/port_guard_site` installs it there (with `OspreyFlow_Build` on the path for its import)."""
    environ["OSPREY_PORT_GUARD"] = "1"
    parts = [p for p in environ.get("PYTHONPATH", "").split(os.pathsep) if p and p not in (_SITE, _BUILD)]
    environ["PYTHONPATH"] = os.pathsep.join([_SITE, _BUILD, *parts])


def neutralise_uvloop() -> None:
    """uvloop connects through libuv, not `socket.socket.connect`, so the guard cannot see it; under
    the guard every uvloop entry point gives asyncio's own loop instead (uvicorn's `auto` loop
    included, which asks uvloop for its loop)."""
    try:
        import uvloop
    except ImportError:
        return
    import asyncio

    uvloop.new_event_loop = asyncio.new_event_loop  # type: ignore[assignment]
    uvloop.EventLoopPolicy = asyncio.DefaultEventLoopPolicy  # type: ignore[assignment,misc]
    uvloop.install = lambda: None  # type: ignore[assignment]
    uvloop.run = asyncio.run  # type: ignore[assignment]


class LeaseNotHeld(ConnectionRefusedError):
    """A connection to the leased test stack from a lane that doesn't hold the lease. A connection
    error on purpose: a test then sees the stack as absent and skips, as when the stack is down."""


def lease_holder(environ: Mapping[str, str]) -> str | None:
    lease = os.path.join(environ.get("OSPREY_LEASE_DIR", os.path.expanduser("~/.ospreyflow")), "stack.lease", "info")
    try:
        with open(lease, encoding="utf-8") as info:
            for line in info:
                if line.startswith("holder="):
                    return line.strip().split("=", 1)[1] or None
    except OSError:
        return None
    return None


class LivePortRefused(RuntimeError):
    """A connection to a live port on this machine, refused before it was made. Not an `OSError`,
    so no client treats it as an unavailable store and skips quietly."""


def in_ci(environ: Mapping[str, str]) -> bool:
    return environ.get("CI", "").strip().lower() == "true"


def _is_this_machine(host: str | None) -> bool:
    if not host:
        return True
    name = host.strip("[]").lower()
    if name == "localhost" or name.endswith(".localhost") or name == "0.0.0.0":  # noqa: S104
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def live_settings(environ: Mapping[str, str]) -> list[str]:
    """Every setting that points this run at a live port on this machine, in words; empty when
    none does."""
    found: list[str] = []
    for name, default in PORT_SETTINGS.items():
        raw = environ.get(name) or default
        try:
            port = int(raw)
        except ValueError:
            continue
        host = environ.get(_HOST_OF[name])
        if port in LIVE_PORTS and _is_this_machine(host):
            how = f"{name}={raw}" if environ.get(name) else f"{name} is not set, so it is {raw}"
            found.append(f"{how}: port {port} is {LIVE_PORTS[port]}")
    for name in URL_SETTINGS:
        value = environ.get(name)
        if not value:
            continue
        parts = urlsplit(value)
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            continue
        if port in LIVE_PORTS and _is_this_machine(parts.hostname):
            found.append(f"{name}={value}: port {port} is {LIVE_PORTS[port]}")
    return found


def refusal(found: list[str]) -> str:
    return (
        "Refused: this test run would reach a live deployment on this machine.\n"
        + "".join(f"  - {line}\n" for line in found)
        + "Nothing was collected and no connection was made. Pin the ports first, for example:\n"
        f"  export {PINNED}\n"
        "(CI's own service containers use these ports on a fresh runner; CI=true allows it.)"
    )


def _address_is_live(address: Any) -> int | None:
    if isinstance(address, tuple) and len(address) >= 2 and isinstance(address[1], int):
        host, port = address[0], address[1]
        if port in LIVE_PORTS and isinstance(host, str) and _is_this_machine(host):
            return port
    return None


def guard_socket(sock_cls: type[socket.socket] = socket.socket) -> Callable[[], None]:
    """Wraps `connect` and `connect_ex` on `sock_cls` so a connection to a live port on this machine
    is refused before it is made. Returns the function that puts them back."""
    original_connect = sock_cls.connect
    original_connect_ex = sock_cls.connect_ex

    def check(address: Any) -> None:
        leased = _leased_ports()
        if isinstance(address, tuple) and len(address) >= 2 and address[1] in leased:
            host = address[0]
            if isinstance(host, str) and _is_this_machine(host) and not in_ci(os.environ):
                lane = os.environ.get("OSPREY_LANE") or None
                holder = lease_holder(os.environ)
                if lane is None or holder != lane:
                    raise LeaseNotHeld(
                        f"Refused before connecting: {host}:{address[1]} is "
                        f"{leased[address[1]]}, and the lease is held by {holder or 'nobody'}, "
                        f"not {lane or 'this run (OSPREY_LANE is not set)'}. Take the lease first "
                        "(OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> \"<purpose>\") and "
                        "run with OSPREY_LANE=<lane>."
                    )
        port = _address_is_live(address)
        if port is not None:
            raise LivePortRefused(
                f"Refused before connecting: {address[0]}:{port} is {LIVE_PORTS[port]}. Tests "
                f"never reach a live deployment; pin the ports ({PINNED})."
            )

    def connect(self: socket.socket, address: Any) -> None:
        check(address)
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        check(address)
        return original_connect_ex(self, address)

    sock_cls.connect = connect  # type: ignore[method-assign]
    sock_cls.connect_ex = connect_ex  # type: ignore[method-assign]

    def restore() -> None:
        sock_cls.connect = original_connect  # type: ignore[method-assign]
        sock_cls.connect_ex = original_connect_ex  # type: ignore[method-assign]

    return restore


def pytest_configure(config: pytest.Config) -> None:
    if in_ci(os.environ):
        return
    found = live_settings(os.environ)
    if found:
        raise pytest.UsageError(refusal(found))
    restore = guard_socket()
    config.add_cleanup(restore)
    neutralise_uvloop()
    propagate(os.environ)


def pytest_report_header(config: pytest.Config) -> str:
    if in_ci(os.environ):
        return "port guard: CI=true, so CI's own service containers may use ports 2480 and 5432"
    return "port guard: on (ports 2480, 5432, 80, 8080 and 8081 on this machine are refused)"
