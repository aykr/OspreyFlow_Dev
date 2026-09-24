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
import socket

from harness.preflight.context import PreflightContext, RenderedOutputMissing
from harness.preflight.result import CheckResult, failed, passed

NAME = "ports"


def declared_ports(compose: dict) -> list[tuple[str, int]]:
    """`(service, host_port)` for every published port, in declaration order. A compose `ports`
    entry is `"HOST:CONTAINER"`; only the host side can collide with anything on this machine."""
    found: list[tuple[str, int]] = []
    for service, spec in (compose.get("services") or {}).items():
        for mapping in (spec or {}).get("ports") or []:
            host_side = str(mapping).split(":")[0]
            if host_side.isdigit():
                found.append((service, int(host_side)))
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
