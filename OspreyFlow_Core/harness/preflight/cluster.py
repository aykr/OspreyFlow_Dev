"""Connectivity to every declared host — `05_DEPLOYMENT.md` §2.1: "and for `cluster` connectivity to
every declared host".

Skipped at `local-lite` and `small`, in those words: §2.1 scopes this check to `cluster`, and
`OspreyConfig` refuses to carry `cluster.hosts` at any other profile anyway, so there is genuinely
nothing to connect to rather than a check being waived.
"""

from __future__ import annotations

import socket

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

NAME = "cluster-connectivity"

#: Short enough that ten unreachable hosts do not make Preflight look hung, long enough that a
#: real host on a slow link is not reported down.
_TIMEOUT_SECONDS = 5.0
#: SSH, because it is what every declared host in this profile is expected to answer on before
#: anything is deployed to it. A deployment-time port would not exist yet at Preflight time.
_PROBE_PORT = 22


def _reachable(address: str, port: int = _PROBE_PORT) -> tuple[bool, str]:
    try:
        with socket.create_connection((address, port), timeout=_TIMEOUT_SECONDS):
            return True, "reachable"
    except OSError as error:
        return False, str(error)


def check(context: PreflightContext) -> CheckResult:
    if context.config.profile.value != "cluster":
        return skipped(
            NAME,
            reason=(
                f"the {context.config.profile.value} profile declares no cluster hosts "
                "(05_DEPLOYMENT.md §2.1 scopes this check to cluster), so there is nothing to "
                "connect to. Not checked."
            ),
        )

    results = [(host, *_reachable(host.address)) for host in context.config.cluster.hosts]
    detail = tuple(f"{host.name} ({host.address}): {why}" for host, _ok, why in results)
    unreachable = [host for host, ok, _why in results if not ok]
    if not unreachable:
        return passed(NAME, detail=detail)

    named = ", ".join(f"{host.name} ({host.address})" for host in unreachable)
    return failed(
        NAME,
        what_is_wrong=(
            f"{len(unreachable)} of {len(results)} declared host(s) did not answer on port "
            f"{_PROBE_PORT}: {named}."
        ),
        what_to_do=(
            "Confirm each host is up and reachable from this machine, that its address in "
            "osprey.yaml is correct, and that no firewall between here and there is dropping the "
            "connection. Applying to a cluster with an unreachable member fails partway through."
        ),
        detail=detail,
    )
