"""Publishes the user repository: the product folder exactly as it is at a commit, copied into an
empty folder — or nothing at all if any file would carry something out that must stay here
(`spec/06_DECISIONS.md` ADR-114 decision 1, Amendment 2 point 4).

    make publish-user-repo COMMIT=HEAD OUT=../../ospreyflow-user     # from the developer repository

**A commit, never the working folder.** The files come from `git archive <commit> OspreyFlow_Core`,
so nothing uncommitted leaves: not the owner's local `osprey.yaml` (which carries a machine path),
not a gitignored data folder, not a scratch file. Pushing the result is the owner's.

**What it refuses**, naming each file (and line, where there is one), before writing anything:

1. any mention of this repository's own folder, `OspreyFlow_Build` — the product must stand alone;
2. an internal demo's data or code, judged against the product's registry *and* the internal demos
   registered beside their code here (`internal_demos/registry.py`), and the fixed internal
   locations the packaging gate already refuses (the local real-data exceptions list, `demo-data/`,
   `OspreyFlow_Data/`);
3. an absolute path into a home folder — `/Users/…`, `/home/…`, `C:\\Users\\…` — which only ever
   names somebody's machine; a home of one of the users the product's own images run as
   (`CONTAINER_HOMES`) is inside a container and passes;
4. the personal authorship identifiers the packaging gate already refuses in a bundle.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tarfile
from collections.abc import Iterable
from pathlib import Path

from internal_demos.registry import ALL

from tools.layout import ROOT
from tools.packaging_gate import AUTHORSHIP_PATTERN, find_internal_demo_data

PRODUCT = "OspreyFlow_Core"
BUILD_NAME = "OspreyFlow_Build"
#: The users the product's own images run as: `/home/<one of these>/` is inside a container, not on
#: anyone's machine (ArcadeDB's backups, the speech model cache).
CONTAINER_HOMES = ("arcadedb", "ubuntu")
#: A path into somebody's home folder, in the three shapes it takes. macOS and Windows home folders
#: never occur inside the product's Linux images, so those are refused outright.
HOME_PATH = re.compile(
    r"/Users/[^/\s'\"`]+/"
    r"|/home/(?!(?:" + "|".join(CONTAINER_HOMES) + r")/)[^/\s'\"`]+/"
    r"|[A-Za-z]:\\\\?Users\\\\?[^\\\s'\"`]+"
)


class PublishRefused(Exception):
    """The publish found something that must not leave, or was pointed somewhere it must not write.
    `findings` names each file (`path:line: reason`, or `path: reason`)."""

    def __init__(self, message: str, findings: list[str] | None = None) -> None:
        super().__init__(message)
        self.findings = findings or []


def _members(commit: str, repo_root: Path) -> dict[str, tuple[bytes, int]]:
    """Each committed file of the product folder at `commit`: its path inside the product, its
    bytes and its mode."""
    archive = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", commit, PRODUCT],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise PublishRefused(f"git could not read {PRODUCT} at {commit!r}: "
                             f"{archive.stderr.decode(errors='replace').strip()}")  # fmt: skip
    found: dict[str, tuple[bytes, int]] = {}
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            inner = member.name.split("/", 1)[1] if "/" in member.name else member.name
            handle = tar.extractfile(member)
            found[inner] = (handle.read() if handle else b"", member.mode)
    return found


def _line_findings(path: str, text: str) -> Iterable[str]:
    for number, line in enumerate(text.splitlines(), start=1):
        if BUILD_NAME in line:
            yield f"{path}:{number}: names {BUILD_NAME}, which the user repository does not have"
        if HOME_PATH.search(line):
            yield f"{path}:{number}: an absolute path into a home folder"
        if AUTHORSHIP_PATTERN.search(line):
            yield f"{path}:{number}: a personal authorship identifier"


def findings_for(files: dict[str, bytes]) -> list[str]:
    """Everything in `files` (path inside the product → bytes) that must not leave."""
    found = [f"{path}: an internal demo's data or code, or the local exceptions list"
             for path in find_internal_demo_data(sorted(files), ALL)]  # fmt: skip
    for path in sorted(files):
        if AUTHORSHIP_PATTERN.search(path) or BUILD_NAME in path:
            found.append(f"{path}: the path itself names what must not leave")
        found.extend(_line_findings(path, files[path].decode("utf-8", errors="ignore")))
    return found


def _check_destination(out: Path, repo_root: Path) -> Path:
    target = out.resolve()
    if target == repo_root.resolve() or repo_root.resolve() in target.parents:
        raise PublishRefused(f"{out} is inside the repository; publish somewhere outside it")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise PublishRefused(f"{out} is not empty; publish into a new or empty folder")
    return target


def publish(commit: str, out: Path, *, repo_root: Path = ROOT) -> list[str]:
    """Copy the product folder at `commit` into `out` and return the paths written, or raise
    `PublishRefused` having written nothing."""
    target = _check_destination(out, repo_root)
    members = _members(commit, repo_root)
    if not members:
        raise PublishRefused(f"{PRODUCT} holds no files at {commit!r}")
    found = findings_for({path: data for path, (data, _mode) in members.items()})
    if found:
        raise PublishRefused(
            f"{len(found)} thing(s) must not leave with the user repository; nothing was written",
            found,
        )
    for path, (data, mode) in members.items():
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(mode & 0o777)
    return sorted(members)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.publish_user_repo", description=__doc__)
    parser.add_argument("commit", help="the commit to publish, for example HEAD or a release tag")
    parser.add_argument("out", type=Path, help="a new or empty folder outside this repository")
    args = parser.parse_args(argv)
    try:
        written = publish(args.commit, args.out)
    except PublishRefused as refusal:
        print(f"publish: {refusal}", file=sys.stderr)
        for finding in refusal.findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print(f"publish: {len(written)} files of {PRODUCT} at {args.commit} written to {args.out}.")
    print("publish: review it, then push it to the user repository yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
