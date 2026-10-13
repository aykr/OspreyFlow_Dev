"""`ospreyflow update` (ADR-114 decision 13, Amendment 6 point 1, Amendment 8).

`--check` asks the user repository's GitHub releases from the machine this runs on and writes the
notice the Conduit reads (`state/update.json`); the deployment itself never calls out. The version
checked is the one the deployment was rendered with (`OSPREY_RELEASE_VERSION` in its
`deployment.env`), not whatever the checkout has moved to since.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from harness.release import (
    GITHUB_API,
    ReleaseRefused,
    check_for_update,
    checkout_version,
    github_repository,
    origin_url,
    write_notice,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def deployed_version(directory: Path, repo_root: Path) -> str:
    """The version the deployment was rendered with; the checkout's if it does not say (rendered
    before B5)."""
    try:
        lines = (directory / "deployment.env").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if line.startswith("OSPREY_RELEASE_VERSION="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
    return checkout_version(repo_root)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(directory: Path, repo_root: Path, *, github_api: str = GITHUB_API) -> int:
    current = deployed_version(directory, repo_root)
    try:
        repository = github_repository(origin_url(repo_root))
    except ReleaseRefused as refused:
        write_notice(directory, {
            "current": current, "checked_at": _now(), "latest": None, "update_available": False,
            "notes": None, "url": None, "problem": str(refused),
        })  # fmt: skip
        print(f"ospreyflow: {refused}", file=sys.stderr)
        return 1
    notice = check_for_update(current, repository, now=_now(), api_base=github_api)
    write_notice(directory, notice)
    if notice["problem"]:
        print(f"ospreyflow: the update check did not answer: {notice['problem']}", file=sys.stderr)
        return 1
    latest = notice["latest"]
    if notice["update_available"]:
        print(f"OspreyFlow {latest} is available (this deployment is {current}).")
        if notice["notes"]:
            print()
            print(notice["notes"])
            print()
        print("Update with: ospreyflow update")
    elif current.startswith("dev-"):
        print(
            f"This deployment builds from its checkout ({current}); it moves with git pull and "
            f"ospreyflow start --build. The newest release is {latest}."
        )
    else:
        print(f"Up to date: {current} is the newest release.")
    return 0


def main(argv: Sequence[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(prog="ospreyflow update", description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="say whether a newer release exists")
    parser.add_argument(
        "--github-api", default=GITHUB_API, help="the GitHub API's address (GitHub Enterprise)"
    )
    args = parser.parse_args(argv)
    if args.check:
        return check(args.deployment, repo_root, github_api=args.github_api)
    print("ospreyflow: only update --check is available yet.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
