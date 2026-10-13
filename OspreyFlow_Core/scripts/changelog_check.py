"""Every release has its changelog section (ADR-114 decision 13, Amendment 8 point 7).

`python -m scripts.changelog_check --tag vX.Y.Z [--changelog PATH] [--notes-out FILE]` finds the
section `## vX.Y.Z — YYYY-MM-DD` in Core's `CHANGELOG.md`, refuses in words if it is missing,
undated, empty or given twice, and writes its body as the release's notes. The user repository's
`release.yml` runs it before anything is built, so it lives in Core (which publishes alone).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

_VERSION = re.compile(r"^v\d+\.\d+\.\d+$")
_HEADING = re.compile(r"^## (\S+)(.*)$", re.M)
_DATED = re.compile(r"^ — \d{4}-\d{2}-\d{2}\s*$")


class ChangelogRefused(Exception):
    """A release the changelog does not describe."""


def release_notes(changelog: str, tag: str) -> str:
    if not _VERSION.match(tag):
        raise ChangelogRefused(f"{tag!r} is not a version (vMAJOR.MINOR.PATCH)")
    headings = list(_HEADING.finditer(changelog))
    mine = [h for h in headings if h.group(1) == tag]
    if not mine:
        raise ChangelogRefused(
            f"CHANGELOG.md has no section for {tag}; add `## {tag} — YYYY-MM-DD`"
        )
    if len(mine) > 1:
        raise ChangelogRefused(f"CHANGELOG.md gives {tag} twice")
    heading = mine[0]
    if not _DATED.match(heading.group(2)):
        raise ChangelogRefused(f"{tag}'s section has no date; write `## {tag} — YYYY-MM-DD`")
    following = [h.start() for h in headings if h.start() > heading.start()]
    body = changelog[heading.end() : min(following, default=len(changelog))].strip()
    if not body:
        raise ChangelogRefused(f"{tag}'s section says nothing")
    return body


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="changelog_check", description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--changelog", type=Path, default=Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    )
    parser.add_argument("--notes-out", type=Path)
    args = parser.parse_args(argv)
    try:
        notes = release_notes(args.changelog.read_text(encoding="utf-8"), args.tag)
    except (ChangelogRefused, OSError) as refused:
        print(f"changelog-check: {refused}", file=sys.stderr)
        return 1
    if args.notes_out is not None:
        args.notes_out.write_text(notes + "\n", encoding="utf-8")
    print(f"changelog-check: {args.tag} has its section.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
