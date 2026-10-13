"""A deployment's version and the update notice (ADR-114 decision 13, Amendment 6 point 1, Amendment
8 points 1–3).

A release is a `vMAJOR.MINOR.PATCH` tag of the user repository. A deployment built from a checkout
is that release if the checkout sits on its tag, else `dev-<short commit>`. `ospreyflow update
--check` asks the repository's GitHub releases — from the machine the command runs on; the
deployment itself never calls out — and writes `state/update.json` in the deployment's folder, which
the Conduit reads (read-only) for Admin → System.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
NOTICE_FILE = "update.json"
STATE_DIR = "state"

_VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_GITHUB_ORIGIN = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


class ReleaseRefused(Exception):
    """A release question that cannot be answered, said in words."""


def _parts(version: str) -> tuple[int, int, int]:
    match = _VERSION.match(version)
    if not match:
        raise ReleaseRefused(f"{version!r} is not a version (vMAJOR.MINOR.PATCH)")
    major, minor, patch = (int(p) for p in match.groups())
    return major, minor, patch


def is_version(text: str) -> bool:
    return _VERSION.match(text) is not None


def newer(candidate: str, than: str) -> bool:
    """Whether `candidate` is a later release than `than`, by number, not by text."""
    return _parts(candidate) > _parts(than)


def _git(repo: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = done.stdout.strip()
    return out if done.returncode == 0 and out else None


def checkout_version(repo: Path) -> str:
    """The release the checkout sits on, else `dev-<short commit>` (`dev-unknown` outside git)."""
    tags = _git(repo, "tag", "--points-at", "HEAD") or ""
    releases = [t for t in tags.splitlines() if is_version(t)]
    if releases:
        return max(releases, key=_parts)
    short = _git(repo, "rev-parse", "--short", "HEAD")
    return f"dev-{short}" if short else "dev-unknown"


def origin_url(repo: Path) -> str:
    return _git(repo, "config", "--get", "remote.origin.url") or ""


def github_repository(origin: str) -> tuple[str, str]:
    """`(owner, repo)` of a GitHub origin — the address `install.sh` cloned from."""
    match = _GITHUB_ORIGIN.match(origin.strip())
    if not match:
        shown = origin or "no origin"
        raise ReleaseRefused(
            f"This checkout's origin ({shown}) is not a GitHub repository, so there are no "
            "releases to look at. A deployment without one is updated from a downloaded bundle: "
            "ospreyflow update --from <bundle>."
        )
    return match.group(1), match.group(2)


def _headers(accept: str) -> dict[str, str]:
    headers = {"Accept": accept, "User-Agent": "ospreyflow-update"}
    # A private repository is read with the host's own token, sent to the API only, kept nowhere.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_releases(owner: str, repo: str, api_base: str) -> list[dict[str, Any]]:
    url = f"{api_base}/repos/{owner}/{repo}/releases?per_page=100"
    headers = _headers("application/vnd.github+json")
    token = headers.get("Authorization")
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - https or loopback
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as refused:
        if refused.code == 404:
            hint = (
                "or GITHUB_TOKEN on this machine cannot read it"
                if token
                else "or it is private: set GITHUB_TOKEN to one that can read it"
            )
            raise ReleaseRefused(
                f"The repository {owner}/{repo} was not found on GitHub ({hint})."
            ) from None
        if refused.code in (403, 429) and refused.headers.get("X-RateLimit-Remaining") == "0":
            raise ReleaseRefused(
                "GitHub's limit on unauthenticated requests was reached; try again in an hour."
            ) from None
        raise ReleaseRefused(f"GitHub answered {refused.code}; try again later.") from None
    except (urllib.error.URLError, OSError, ValueError) as unreachable:
        raise ReleaseRefused(f"The check could not reach GitHub ({unreachable}).") from None
    if not isinstance(body, list):
        raise ReleaseRefused("GitHub answered in a form this check does not understand.")
    return [r for r in body if isinstance(r, dict)]


def check_for_update(
    current: str, repository: tuple[str, str], *, now: str, api_base: str = GITHUB_API
) -> dict[str, Any]:
    """The notice: the newest published release (drafts, pre-releases and tags that are not
    versions are never offered), and whether it is newer than `current`. A deployment built from a
    checkout (`dev-…`) is never told to update: it moves with its checkout. A check that cannot
    answer says why and offers nothing."""
    notice: dict[str, Any] = {
        "current": current, "checked_at": now, "latest": None, "update_available": False,
        "notes": None, "url": None, "problem": None,
    }  # fmt: skip
    owner, repo = repository
    try:
        releases = _fetch_releases(owner, repo, api_base)
    except ReleaseRefused as why:
        notice["problem"] = str(why)
        return notice
    published = _published(releases)
    if not published:
        notice["problem"] = f"{owner}/{repo} has published no release yet."
        return notice
    latest = max(published, key=lambda r: _parts(str(r["tag_name"])))
    notice["latest"] = latest["tag_name"]
    notice["notes"] = latest.get("body") or None
    notice["url"] = latest.get("html_url") or None
    notice["update_available"] = is_version(current) and newer(latest["tag_name"], current)
    return notice


def _published(releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in releases
        if not r.get("draft") and not r.get("prerelease") and is_version(str(r.get("tag_name")))
    ]


def find_release(
    repository: tuple[str, str], tag: str | None, *, api_base: str = GITHUB_API
) -> dict[str, str]:
    """The release to update to — `tag`, or the newest published — with its notes and its
    `versions.lock`, fetched as a release asset through the API (so a private repository is read
    with the host's token). Refused in words when there is none to apply."""
    if tag is not None and not is_version(tag):
        raise ReleaseRefused(f"{tag!r} is not a version (vMAJOR.MINOR.PATCH)")
    owner, repo = repository
    published = _published(_fetch_releases(owner, repo, api_base))
    if tag is not None:
        chosen = [r for r in published if r["tag_name"] == tag]
        if not chosen:
            raise ReleaseRefused(f"{owner}/{repo} has no published release {tag}.")
        release = chosen[0]
    elif published:
        release = max(published, key=lambda r: _parts(str(r["tag_name"])))
    else:
        raise ReleaseRefused(f"{owner}/{repo} has published no release yet.")
    by_name = {str(a.get("name")): a for a in release.get("assets") or []}
    if "versions.lock" not in by_name:
        raise ReleaseRefused(
            f"{release['tag_name']} has no versions.lock, so it cannot be applied: it says which "
            "image digests the release is."
        )
    if "versions.lock.sigstore.json" not in by_name:
        raise ReleaseRefused(
            f"{release['tag_name']} has no signed versions.lock (versions.lock.sigstore.json), so "
            "its third-party images cannot be trusted."
        )
    return {
        "tag": str(release["tag_name"]),
        "notes": str(release.get("body") or ""),
        "lock": _asset(by_name["versions.lock"], release["tag_name"]),
        "lock_signature": _asset(by_name["versions.lock.sigstore.json"], release["tag_name"]),
    }


def _asset(asset: dict[str, Any], tag: str) -> str:
    request = urllib.request.Request(
        str(asset["url"]), headers=_headers("application/octet-stream")
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return str(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as failed:
        raise ReleaseRefused(f"{tag}'s {asset.get('name')} could not be read ({failed}).") from None


def write_notice(deployment: Path, notice: dict[str, Any]) -> Path:
    state = deployment / STATE_DIR
    state.mkdir(exist_ok=True)
    path = state / NOTICE_FILE
    path.write_text(json.dumps(notice, indent=2) + "\n", encoding="utf-8")
    return path


def read_notice(state: Path) -> dict[str, Any] | None:
    """The last check, or `None` when there has been none (or its file cannot be read)."""
    try:
        loaded = json.loads((state / NOTICE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None
