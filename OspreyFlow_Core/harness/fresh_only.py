"""v0.6.0 is installed fresh (the owner's ruling of 15 November 2026, v0.6.0's item `rf`): no path
moves a deployment of an earlier release onto it. `ospreyflow update` (`harness.update`), an install
over an existing deployment (`harness.apply`) and the cloud-platform runbook's run over a namespace
already holding a deployment (`INSTALL.md` step 1, which calls this module) each refuse, in the same
words, before anything is changed. A deployment at v0.6.0 or later is not refused: an update within
v0.6 moves as before.

A deployment's release is the `OSPREY_RELEASE_VERSION` it was rendered with (its `deployment.env`,
or on a cluster the `ospreyflow-env` ConfigMap). One that names none was rendered before releases
were stamped, so it is earlier still.

    python -m harness.fresh_only --installed <its version, or nothing>   # exit 1 with the words
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

#: The release from which a deployment is installed fresh, never moved onto.
FRESH_FROM = "v0.6.0"
_RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)")


def _release(text: str | None) -> tuple[int, int, int] | None:
    """`v0.6.0`, `v0.6.0-dev…` or `v0.6.1` as numbers; anything else (`dev-<commit>`, nothing) as
    `None`. A checkout stamped `v0.6.0-dev` is v0.6.0's code."""
    found = _RELEASE.match(text or "")
    return None if found is None else (int(found[1]), int(found[2]), int(found[3]))


def installed_version(env_text: str) -> str | None:
    """The `OSPREY_RELEASE_VERSION` a deployment's environment file names, if any."""
    for line in env_text.splitlines():
        if line.startswith("OSPREY_RELEASE_VERSION="):
            return line.split("=", 1)[1].strip() or None
    return None


def refusal(installed: str | None, installing: str) -> str | None:
    """The words refusing to move a deployment of `installed` onto `installing`, or `None` when the
    move is allowed: `installing` is before v0.6.0, or the deployment is at v0.6.0 or later."""
    target = _release(installing)
    fresh = _release(FRESH_FROM)
    assert fresh is not None
    if target is None or target < fresh:
        return None
    have = _release(installed)
    if have is not None and have >= fresh:
        return None
    shown = installed or "from before releases were stamped"
    return (
        f"{FRESH_FROM} is installed fresh; this deployment is {shown}, and nothing moves it onto "
        f"{installing}. Install {installing} as a new deployment, in a place of its own (a folder, "
        f"or on a cluster a namespace); this one is left on {shown}, unchanged."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harness.fresh_only", description=__doc__)
    parser.add_argument("--installed", default="", help="the deployment's OSPREY_RELEASE_VERSION")
    parser.add_argument(
        "--installing", help="the release being installed; this checkout's if not given"
    )
    args = parser.parse_args(argv)
    installing = args.installing
    if installing is None:
        from harness.release import checkout_version

        installing = checkout_version(Path(__file__).resolve().parents[1])
    why = refusal(args.installed or None, installing)
    if why is not None:
        print(why, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
