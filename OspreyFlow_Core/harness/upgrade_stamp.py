"""The cached-upgrade trap, closed (v0.6.0, the owner's word of 15 November 2026).

Every image we build ends with one distribution upgrade (`apt-get upgrade`, or `apk upgrade` for the
Glass's nginx), so a base's security fixes arrive even when the base image has not been rebuilt
(`test_images_built_fresh.py`). But that layer's text never changes, and Docker keys a layer on its
text and its parent: a builder holding a cached copy reuses it, and keeps whatever the distribution
held the day that copy was made. `--pull` does not reach it when the base is pinned or unchanged.
Found on the test server on 15 November 2026: the Superset image kept PostgreSQL's client libraries
at 15.19-0+deb12u1, 192 HIGH CVEs that Debian had fixed in 15.20-0+deb12u1.

So each Dockerfile declares `ARG OSPREY_UPGRADE_STAMP` just before its upgrade and names it in that
step, and every place that builds passes the day's date: the layer's key changes once a day, and
every later step is rebuilt on top of it. A build arg rather than `--no-cache-filter`, because an
arg reaches every builder we use the same way (`docker build`, `docker buildx build`, and
`docker compose build`), and BuildKit's filter does not.

The places that build pass `build_args()`: `ospreyflow start --build` (`scripts/refresh.py`), the
harness's install and apply (`harness/apply.py`), and the local release (`tools/release_local.py`).
`ospreyflow images push` (`cli/ospreyflow/images.py`, the cloud-platform install's step 3)
computes the same stamp itself, since the command imports nothing of the product (ADR-114
decision 3).
The Makefiles and the workflows pass `$(date -u +%F)` themselves. Held by
`tests/test_upgrade_stamp.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

#: The build arg each upgrading Dockerfile declares before its upgrade step.
UPGRADE_STAMP_ARG = "OSPREY_UPGRADE_STAMP"


def upgrade_stamp(now: datetime | None = None) -> str:
    """Today's date in UTC, `YYYY-MM-DD`: the value changes once a day, and is the same for every
    image built that day."""
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%d")


def build_args(now: datetime | None = None) -> list[str]:
    """The arguments a `docker build` or `docker compose build` takes to pass the stamp."""
    return ["--build-arg", f"{UPGRADE_STAMP_ARG}={upgrade_stamp(now)}"]


__all__ = ["UPGRADE_STAMP_ARG", "build_args", "upgrade_stamp"]
