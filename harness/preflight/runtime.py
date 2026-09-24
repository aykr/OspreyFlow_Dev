"""Container runtime present and its version — `05_DEPLOYMENT.md` §2.1's fifth check.

The harness drives the orchestrator (§2.4), so a missing or unreachable runtime is not a problem
that surfaces later as a confusing container error: it is the first thing that makes Launch
impossible, and it is cheap to say so plainly.

**A daemon that is installed but not running is a different failure from one that is absent**, and
the remedies are different too, so the two are reported separately rather than as one "docker not
available".
"""

from __future__ import annotations

import shutil
import subprocess

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed

NAME = "container-runtime"


def check(context: PreflightContext) -> CheckResult:
    binary = shutil.which(context.container_runtime)
    if binary is None:
        return failed(
            NAME,
            what_is_wrong=(
                f"{context.container_runtime!r} is not on PATH, so nothing can start this "
                "deployment's containers."
            ),
            what_to_do=(
                "Install Docker Desktop (macOS, Windows) or the Docker engine (Linux), then "
                "re-check. Podman works too if you set the runtime accordingly."
            ),
        )

    try:
        version = subprocess.run(
            [binary, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return failed(
            NAME,
            what_is_wrong=f"{binary} could not be run: {error}",
            what_to_do="Check the installation, then re-check.",
            detail=(f"binary: {binary}",),
        )

    if version.returncode != 0 or not version.stdout.strip():
        return failed(
            NAME,
            what_is_wrong=(
                f"{context.container_runtime} is installed at {binary} but its daemon did not "
                f"answer: {version.stderr.strip() or 'no server version reported'}"
            ),
            what_to_do=(
                "Start the daemon — open Docker Desktop, or `systemctl start docker` on Linux — "
                "and re-check. The client being installed is not the same as the daemon running."
            ),
            detail=(f"binary: {binary}",),
        )

    return passed(NAME, detail=(f"{context.container_runtime} server {version.stdout.strip()}",))
