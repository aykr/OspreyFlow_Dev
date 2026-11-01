"""The release this deployment runs, read in one place (the owner's answer of 1 November 2026; GDS
remediation O1).

The single source is the release tag the deployment was rendered from: `harness.render.
release_version` writes it to `deployment.env` as `OSPREY_RELEASE_VERSION` (`vMAJOR.MINOR.PATCH`, or
`dev-<short commit>` off a tag; ADR-114 Amendment 8), and the Conduit reads it from its environment.
Admin → System and the OpenAPI document's `info.version` both say this value; neither has a version
of its own. `OSPREY_VERSION` is the older name, still read. A process started with neither says
`dev-unknown`, as `harness.release.checkout_version` does outside git, never FastAPI's `0.1.0`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

UNKNOWN = "dev-unknown"


def release_version(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return env.get("OSPREY_RELEASE_VERSION") or env.get("OSPREY_VERSION") or UNKNOWN


def deployment_version(environ: Mapping[str, str] | None = None) -> str | None:
    """The version Admin → System shows: the same value, or nothing when none was rendered."""
    env = os.environ if environ is None else environ
    return env.get("OSPREY_RELEASE_VERSION") or env.get("OSPREY_VERSION")
