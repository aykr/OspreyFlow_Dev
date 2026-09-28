"""`make ci-status` / the release workflow's own gate — round 13cg.

**Why this exists.** Round 13ce's own report noted, in passing, that GitHub Actions "has not run
on `main` since 22 September." Investigating that finding this round (rather than repeating it)
found it was itself wrong in a more serious way: `gh api repos/{owner}/{repo}/actions/runs` on the
real repository returns `total_count: 0` — not "stopped 22 September", but **no workflow run has
ever completed on this repository, at any time**, despite `ci.yml` being present since 13 September
and hundreds of pushes to `main` since. The specific run the earlier report cited
(`35756063850` at `12810f4`) 404s on direct lookup; it cannot be reproduced and this module does
not repeat the claim.

**What was ruled out, checked directly rather than assumed.** `GET /repos/{owner}/{repo}/actions/
permissions` reports `enabled: true, allowed_actions: "all"`; the workflow's own state is
`"active"`; the repository is not a fork; the owning account is not suspended
(`suspended_at: null` on the authenticated user). None of that explains zero runs, ever, against
continuous pushes to `main`.

**What was not ruled out, because it needs scopes this session's token does not have and should
not request for itself** (`GET /users/{owner}/settings/billing/actions` needs the `user` OAuth
scope; `gh auth refresh` for it is an interactive step, not something a maker round takes
unattended). The leading candidate is an Actions spending limit of $0 with no included minutes
left, or an unverified account email — both silently prevent a run from ever being *created*,
which is consistent with `total_count: 0` rather than a run existing with a `startup_failure`
conclusion. **This is the repository/account setting the owner has to check**, at
`https://github.com/settings/billing` (Actions) and `https://github.com/settings/emails`.

**What this module does about it.** It cannot fix an account setting. What it *can* fix is the
next occurrence of this exact failure being silent — the actual defect round 13ce's own note
disclosed, and the reason this is a gate rather than a paragraph. `latest_ci_status` distinguishes
three states a caller needs to tell apart, because "no data" and "red" have the same consequence
(nothing was proven) but different fixes:

- `never_run` — no check run has ever reported for this ref. What round 13ce found, restated
  precisely rather than dated to a run that does not exist.
- `pending` — a check run for this ref exists and has not finished. Not a failure by itself, but
  not evidence of green either — a caller that needs green must not treat "still running" as
  "passed".
- `failed` — a check run completed with a conclusion other than `success`/`neutral`/`skipped`,
  named.
- `success` — every check run for this ref completed with `success`, `neutral` or `skipped`.

`main()` treats every state but `success` as exit 1. Wired into `release.yml` as a gate other jobs
depend on (`ci-status-gate`), using the run's own `GITHUB_TOKEN` — the same class of fix as
`decision_log_publication_check.py`'s: a real, hand-kept table that fires safely on the side that
was silent before.

**Non-vacuous, proven the same way**: `tests/test_ci_status_check.py` fixes a fake GitHub API
transport to each of the four states above and asserts `latest_ci_status` reports the one it
actually saw — including the case that matters most here, no check runs at all.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A completed check run in any of these is not a failure — `neutral`/`skipped` are legitimate
#: outcomes for a job that chose not to run its assertion (a path filter, a matrix leg not
#: applicable), not evidence of anything broken.
_NON_FAILING_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})


@dataclass(frozen=True)
class CiStatus:
    state: str  # "never_run" | "pending" | "failed" | "success"
    detail: str

    @property
    def is_green(self) -> bool:
        return self.state == "success"


def latest_ci_status(owner: str, repo: str, ref: str, *, client: httpx.Client) -> CiStatus:
    """The aggregate state of every check run GitHub has recorded for `ref` — paginated, since a
    ref can carry more check runs than one page returns once `ci.yml` grows more jobs."""
    runs: list[dict[str, object]] = []
    url: str | None = f"/repos/{owner}/{repo}/commits/{ref}/check-runs?per_page=100"
    while url is not None:
        response = client.get(url)
        response.raise_for_status()
        body = response.json()
        runs.extend(body.get("check_runs", []))
        url = _next_page_url(response)

    if not runs:
        return CiStatus(
            "never_run",
            f"no check run has ever reported for {owner}/{repo}@{ref} — see this module's own "
            "docstring for what that does and does not rule out",
        )

    incomplete = [r for r in runs if r.get("status") != "completed"]
    if incomplete:
        names = ", ".join(sorted({str(r.get("name")) for r in incomplete}))
        return CiStatus("pending", f"still running: {names}")

    failed = [r for r in runs if r.get("conclusion") not in _NON_FAILING_CONCLUSIONS]
    if failed:
        names = ", ".join(sorted({str(r.get("name")) for r in failed}))
        return CiStatus("failed", f"failing check run(s): {names}")

    return CiStatus("success", f"{len(runs)} check run(s) green")


def _next_page_url(response: httpx.Response) -> str | None:
    link = response.headers.get("link")
    if not link:
        return None
    for part in link.split(","):
        url, _, rel = part.partition(";")
        if 'rel="next"' in rel:
            return str(url.strip(" <>"))
    return None


def _origin_owner_repo() -> tuple[str, str]:
    """Parsed from `git remote get-url origin` — the same source of truth every other script in
    this repository that needs to know "which repository" reads, rather than a second, possibly
    stale copy of the name in a config file."""
    url = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if match is None:
        raise ValueError(f"origin {url!r} is not a github.com remote")
    return match.group(1), match.group(2)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _token() -> str:
    """`GH_TOKEN`/`GITHUB_TOKEN` first — what a workflow's own environment sets, and what an
    operator can export by hand. Falling back to `gh auth token` (read-only; it prints the token
    already stored, never authenticates or writes anything) is a convenience for a developer
    running this locally with `gh` already signed in, matching how `DEMO_GUIDE.md` already treats
    `gh` as an available tool in this environment rather than one this repository vendors."""
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "no GH_TOKEN/GITHUB_TOKEN set and `gh auth token` failed — this check needs a token "
            "with read access to Actions runs"
        ) from exc
    return result.stdout.strip()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.ci_status_check",
        description="Refuses (exit 1) unless every check run for a ref reports success.",
    )
    parser.add_argument(
        "--repo", help="owner/repo — read from `git remote get-url origin` if omitted"
    )
    parser.add_argument("--ref", help="a commit sha or branch — defaults to HEAD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    owner, repo = args.repo.split("/", 1) if args.repo else _origin_owner_repo()
    ref = args.ref or _head_sha()

    with httpx.Client(
        base_url="https://api.github.com",
        headers={"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json"},
        timeout=30.0,
    ) as client:
        status = latest_ci_status(owner, repo, ref, client=client)

    print(f"ci-status: {owner}/{repo}@{ref}: {status.state} — {status.detail}")
    if not status.is_green:
        print(
            "ci-status: refusing. A red or never-run CI has proven nothing about this commit — "
            "see process/07_BUILD_PLAN.md's round 13cg finding for what a `never_run` state here "
            "has already once meant on this repository."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
