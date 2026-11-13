"""A committed file's text as git holds it, not as the working tree has it.

**Why a test that means "the committed `osprey.yaml`" cannot read the file on disk.** Every lane
worktree's `OspreyFlow_Core/osprey.yaml` is the owner's own, uncommitted copy:
`scripts/lanes_launch.sh`'s `setup` copies it from the main checkout and marks it
`--skip-worktree`, so `git status` stays clean while the file differs from the commit. Found 13
November 2026: `test_the_committed_osprey_yaml_still_validates` failed in every lane on the
owner's `default: osm-local-great-britain` while main's committed file says `osm-local`, and the
two other readers of the committed config (rule 9's tier-1 check and the bundle's fixture) were
testing the owner's config, not the repository's. `git show HEAD:<path>` reads the commit,
whatever the working copy holds.

No fallback to the working copy: a test that silently read the file on disk when git could not
answer would be the defect this module exists to remove. Every place these tests run (a lane, the
main checkout, CI's `actions/checkout`) is a git checkout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def committed_text(path: Path) -> str:
    """`path`'s text at `HEAD` of the repository it is in. Raises if git cannot answer (not a
    checkout, or the file is not committed) rather than reading the working copy."""
    result = subprocess.run(
        ["git", "-C", str(path.parent), "show", f"HEAD:./{path.name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git cannot show the committed {path}: {result.stderr.strip()}")
    return result.stdout


def committed_copy(path: Path, into: Path) -> Path:
    """The committed `path` written to `into/<its name>`, for a loader that takes a path."""
    into.mkdir(parents=True, exist_ok=True)
    copy = into / path.name
    copy.write_text(committed_text(path), encoding="utf-8")
    return copy
