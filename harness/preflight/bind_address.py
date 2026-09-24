"""Every service's bind address is consistent, and printed — a rehearsal-derived check.

**The finding this exists for, in `DEMO_GUIDE.md`'s own words:** "the rehearsal found the Vite dev
server on this machine resolved `localhost` to `::1` (IPv6) only, so `127.0.0.1:5173` did not
connect at all." Nothing was misconfigured and nothing errored — a service bound one family, a
client dialled the other, and the connection simply never happened.

**So this check prints as well as judges.** §2.1 requires a failure to explain what is wrong; for
this class of fault the operator also needs to see what each side actually resolved to, because the
symptom (a page that will not load) looks identical to half a dozen unrelated problems. The detail
lines are the deliverable here as much as the status is.
"""

from __future__ import annotations

import socket

from harness.preflight.context import PreflightContext, RenderedOutputMissing
from harness.preflight.result import CheckResult, failed, passed

NAME = "bind-address"


def _families_for(hostname: str) -> set[str]:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return set()
    return {"IPv4" if info[0] == socket.AF_INET else "IPv6" for info in infos}


def check(context: PreflightContext) -> CheckResult:
    try:
        compose = context.rendered_compose()
    except RenderedOutputMissing as missing:
        return failed(
            NAME,
            what_is_wrong=(
                f"there is no rendered compose file to read bind addresses from: {missing}"
            ),
            what_to_do="Run `python -m harness.render` for this profile, then re-check.",
        )

    published: list[str] = []
    for service, spec in (compose.get("services") or {}).items():
        for mapping in (spec or {}).get("ports") or []:
            parts = str(mapping).split(":")
            host_address = parts[0] if len(parts) > 2 else "0.0.0.0"
            published.append(f"{service}: publishes on {host_address}")

    localhost_families = _families_for("localhost")
    detail = (
        *published,
        "'localhost' on this machine resolves to: "
        + (", ".join(sorted(localhost_families)) or "nothing"),
        "published ports above bind IPv4 (0.0.0.0) unless an address is given explicitly",
    )

    if not localhost_families:
        return failed(
            NAME,
            what_is_wrong="'localhost' does not resolve on this machine at all.",
            what_to_do=(
                "Add `127.0.0.1 localhost` to /etc/hosts. Every URL in the runbook and the demo "
                "guide uses `localhost`, and none of them will connect until it resolves."
            ),
            detail=detail,
        )

    if localhost_families == {"IPv6"}:
        return failed(
            NAME,
            what_is_wrong=(
                "'localhost' resolves to IPv6 (::1) only on this machine, while the published "
                "ports above bind IPv4. A browser or client dialling `localhost` will reach "
                "nothing, with no error from either side — the connection is simply never made. "
                "This is the exact failure the 23 September rehearsal hit on the Vite dev server."
            ),
            what_to_do=(
                "Use `127.0.0.1` rather than `localhost` in the URLs you open, or add a "
                "`127.0.0.1 localhost` entry ahead of the `::1` one in /etc/hosts so the name "
                "resolves to both families."
            ),
            detail=detail,
        )

    return passed(NAME, detail=detail)
