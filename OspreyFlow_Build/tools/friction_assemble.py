"""Assemble the lanes' friction-log fragments into `process/07_BUILD_PLAN.md` (ADR-142 decision 5; P6).

Lanes run in parallel, so no lane edits the friction log: each change writes its row as its own file,
`process/friction/<yyyy-mm-dd>-<lane>-<slug>.md`, holding exactly one row of the table, its last cell
ending "Hash: recorded at merge." Only the orchestrator runs this, after a merge:

    python -m tools.friction_assemble --hash <merge hash> [--dry-run]

It appends the rows after the friction log's last row, in date order (then by file name), fills each
"Hash: recorded at merge." with the merge's hash, writes the build plan, and only then removes the
fragments. It refuses, writing nothing, if a fragment holds two rows or none, or a row that is not five
cells. A row whose hash is already filled keeps it: a hash is never overwritten. Files in
`process/friction/` not named like a fragment (its `README.md`) are left alone.

Its red-then-green proof is `tests/test_friction_assemble.py` (rule 15).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.layout import REPO as REPO_ROOT

FRICTION_DIR = REPO_ROOT / "process" / "friction"
BUILD_PLAN = REPO_ROOT / "process" / "07_BUILD_PLAN.md"
PLACEHOLDER = "Hash: recorded at merge."

_FRAGMENT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+)-[a-z0-9-]+\.md$")
_ROW = re.compile(r"^\| \d{4}-\d{2}-\d{2} \|.*\|\s*$")
_HASH = re.compile(r"^[0-9a-f]{7,40}$")


class FragmentError(ValueError):
    pass


@dataclass(frozen=True)
class Fragment:
    path: Path
    date: str
    row: str


def _cells(row: str) -> int:
    # An escaped pipe (`\|`) inside a cell is text, not a border.
    return len(re.findall(r"(?<!\\)\|", row)) - 1


def read_fragments(friction_dir: Path) -> list[Fragment]:
    fragments = []
    for path in sorted(friction_dir.glob("*.md")):
        name = _FRAGMENT_NAME.match(path.name)
        if name is None:
            continue
        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if _ROW.match(line)]
        if len(rows) != 1:
            raise FragmentError(f"{path.name} holds {len(rows)} friction-log rows, not one")
        row = rows[0].rstrip()
        if _cells(row) != 5:
            raise FragmentError(f"{path.name}'s row has {_cells(row)} cells, not five")
        if not row.startswith(f"| {name.group(1)} |"):
            raise FragmentError(f"{path.name}'s row is not dated {name.group(1)}, as its name is")
        fragments.append(Fragment(path, name.group(1), row))
    return sorted(fragments, key=lambda f: (f.date, f.path.name))


def fill(row: str, merge_hash: str) -> str:
    if PLACEHOLDER not in row:
        return row  # already filled: never overwritten
    return row.replace(PLACEHOLDER, f"{merge_hash}.")


def assembled(plan: str, rows: list[str]) -> str:
    lines = plan.split("\n")
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "## Friction log"), None
    )
    if start is None:
        raise FragmentError("the build plan has no '## Friction log' heading")
    last = max((i for i, line in enumerate(lines) if i > start and _ROW.match(line)), default=None)
    if last is None:
        raise FragmentError("the build plan's friction log has no row to append after")
    return "\n".join(lines[: last + 1] + rows + lines[last + 1 :])


def assemble(
    merge_hash: str,
    friction_dir: Path = FRICTION_DIR,
    build_plan: Path = BUILD_PLAN,
    dry_run: bool = False,
) -> list[str]:
    """Append every fragment's row, filled with `merge_hash`; return the rows appended."""
    if not _HASH.match(merge_hash):
        raise FragmentError(f"{merge_hash!r} is not a commit hash")
    fragments = read_fragments(friction_dir)
    rows = [fill(f.row, merge_hash) for f in fragments]
    if not rows or dry_run:
        return rows
    text = assembled(build_plan.read_text(encoding="utf-8"), rows)
    tmp = build_plan.with_name(build_plan.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, build_plan)
    for fragment in fragments:  # only once the table is written
        fragment.path.unlink()
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hash", required=True, help="the merge commit's hash")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        rows = assemble(args.hash, dry_run=args.dry_run)
    except FragmentError as error:
        print(f"friction-assemble: refused, nothing written: {error}", file=sys.stderr)
        return 1
    verb = "would append" if args.dry_run else "appended"
    print(f"friction-assemble: {verb} {len(rows)} row(s) to process/07_BUILD_PLAN.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
