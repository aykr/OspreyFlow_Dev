"""Port availability for every service the **rendered compose file** declares — §2.1's fourth check.

Reading the rendered file rather than the profile is the point. A check that asserted "8080 and 8000
are free" would keep passing after a render that moved them, and would say nothing at all about a
service added to the compose file later. Every published port in
`deploy/generated/<profile>/compose.yaml` is read out and tested by actually binding it.

**Binding is the test, not a scan of `lsof`.** A port can be held by a process this user cannot see;
the question Preflight has to answer is "can this deployment bind it", and the only honest way to
answer that is to try.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
from collections.abc import Mapping
from typing import Any

from harness.preflight.context import PreflightContext, RenderedOutputMissing
from harness.preflight.result import CheckResult, failed, passed

NAME = "ports"


#: `${VAR:-default}` as compose writes it. Stage 2 §5a made every published host port overridable,
#: which means the host side of a `ports` entry is no longer a bare number — and a naive
#: `split(":")` does not even tokenise it correctly, because `:-` contains the same separator.
#: Found by this module's own test the moment the renderer changed: without this, `declared_ports`
#: returned nothing and the whole check passed vacuously on every deployment.
_INTERPOLATED = re.compile(r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>\d+))?\}$")


def _host_port(token: str, environ: Mapping[str, str]) -> int | None:
    """The port that will actually be published: the environment's value when the variable is set,
    the compose default otherwise. Checking the default when the environment overrides it would
    check a port the deployment is not going to use."""
    token = token.strip()
    if token.isdigit():
        return int(token)
    match = _INTERPOLATED.match(token)
    if match is None:
        return None
    value = environ.get(match["name"]) or match["default"]
    return int(value) if value and value.isdigit() else None


def declared_ports(
    compose: dict[str, Any], environ: Mapping[str, str] | None = None
) -> list[tuple[str, int]]:
    """`(service, host_port)` for every published port, in declaration order.

    A compose `ports` entry is `"HOST:CONTAINER"` or `"IP:HOST:CONTAINER"`; only the host side can
    collide with anything on this machine. The host side may be an interpolated variable, so it is
    resolved against the environment the deployment will actually run with.
    """
    environ = os.environ if environ is None else environ
    found: list[tuple[str, int]] = []
    for service, spec in (compose.get("services") or {}).items():
        for mapping in (spec or {}).get("ports") or []:
            text = str(mapping)
            # Split off the container side only: the host side may itself contain `:-`.
            host_side, _, _container = text.rpartition(":")
            if not host_side:
                continue
            # An explicit bind address, `IP:HOST:CONTAINER`, leaves the IP on the front.
            if host_side.count(":") and not host_side.startswith("${"):
                host_side = host_side.rpartition(":")[2]
            port = _host_port(host_side, environ)
            if port is not None:
                found.append((service, port))
    return found


def _is_bindable(port: int) -> bool:
    """Binds for real, with `SO_REUSEADDR` deliberately **not** set: the deployment's own containers
    will not set it either, so a port in `TIME_WAIT` that `SO_REUSEADDR` would paper over is a port
    this check should still report."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def check(context: PreflightContext) -> CheckResult:
    try:
        compose = context.rendered_compose()
    except RenderedOutputMissing as missing:
        return failed(
            NAME,
            what_is_wrong=f"there is no rendered compose file to read ports from: {missing}",
            what_to_do="Run `python -m harness.render` for this profile, then re-check.",
        )

    ports = declared_ports(compose)
    if not ports:
        return passed(NAME, detail=("the rendered compose file publishes no host ports",))

    taken = [(service, port) for service, port in ports if not _is_bindable(port)]
    detail = tuple(f"{service}: {port}" for service, port in ports)
    if not taken:
        return passed(NAME, detail=detail)

    listed = ", ".join(f"{port} ({service})" for service, port in taken)
    return failed(
        NAME,
        what_is_wrong=(
            f"{len(taken)} of {len(ports)} port(s) this deployment publishes are already in use: "
            f"{listed}. Launch would fail partway through, leaving some containers up."
        ),
        what_to_do=(
            "Stop whatever holds them — `lsof -nP -iTCP -sTCP:LISTEN | grep <port>` names the "
            "process — or change the published ports in osprey.yaml and re-render. A previous "
            "`make dev-up` stack is the usual culprit; `make dev-down` clears it."
        ),
        detail=detail,
    )
