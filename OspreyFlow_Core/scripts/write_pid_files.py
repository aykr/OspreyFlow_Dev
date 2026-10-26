"""Writes the Prison Intelligence Dataset's generated files to a folder (ADR-120 Amendment 9).

    python -m scripts.write_pid_files --out DIR [--profile demo|scale]

`--out` is required and must be outside the git working tree: the files, about 100,000 call rows
among them, are never committed (the naming rule and rule 9), so a path inside the repository is
refused before anything is written. It writes the CSV files, `pictures/`, for the demo profile
`pid_cohort_list.txt` (the 40 identifiers the add-many scene pastes, ADR-128), and `manifest.json`
(rows, bytes and SHA-256 per file, and the planted counts and row positions; no timestamps), then,
for a profile with pictures, `contact_sheet.png`, and prints a table of what it wrote.

Plain generation: no store, no network.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from demo_fixtures import pid_files, pid_pictures, pid_plan

_PEOPLE = ("principal", "brother", "coordinator", "mother", "sister", "friend", "partner", "payer",
           "calder_1")  # fmt: skip
SHEET_COLUMNS = 6
SHEET_TILE = 128


def repository_root(start: Path) -> Path | None:
    """The git working tree `start` lies in: the nearest parent holding `.git`, or `None`."""
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    return None


def inside_repository(path: Path) -> bool:
    """Whether `path` (resolved, so a symlink or `..` cannot hide it) is the working tree or in
    it."""
    root = repository_root(Path(__file__).resolve().parent)
    if root is None:
        return False
    resolved = path.expanduser().resolve()
    return resolved == root or root in resolved.parents


def picture_sample(plan: pid_plan.Plan) -> list[str]:
    """The subjects on the contact sheet: the principal, the brother, the coordinator, six other
    people, the three establishments, a hotspot yard and an ordinary yard, a wing, a handset and
    both groups, in that order; whichever the plan does not hold is left out."""
    held = set(plan.picture_subjects)
    hotspot = sorted(f"yard:{code}" for code in pid_plan.HOTSPOT_YARDS)[0]
    ordinary = sorted(
        f"yard:{code}" for code in pid_plan.YARD_COUNTS if code not in pid_plan.HOTSPOT_YARDS
    )[0]
    wanted = [
        *_PEOPLE,
        *sorted(k for k in held if k.startswith("est:")),
        hotspot,
        ordinary,
        "wing:F",
        "handset:pryce",
        *sorted(k for k in held if k.startswith("ocg:")),
    ]
    return [k for k in wanted if k in held]


def write_contact_sheet(plan: pid_plan.Plan, out_dir: Path) -> Path:
    """`contact_sheet.png`: the sample's pictures, read back from `out_dir/pictures/`, six to a row
    at 128 pixels."""
    sheet = out_dir / "contact_sheet.png"
    pictures = [
        (out_dir / "pictures" / (key.replace(":", "_") + ".png")).read_bytes()
        for key in picture_sample(plan)
    ]
    sheet.write_bytes(
        pid_pictures.contact_sheet(pictures, columns=SHEET_COLUMNS, tile=SHEET_TILE)
    )
    return sheet


def _table(report: pid_files.WriteReport) -> str:
    width = max([len(f.name) for f in report.files] + [4])
    lines = [f"{'file':<{width}}  {'rows':>10}  {'bytes':>12}  sha256"]
    for f in report.files:
        lines.append(f"{f.name:<{width}}  {f.rows:>10,}  {f.bytes:>12,}  {f.sha256}")
    for entry in report.lists:
        lines.append(
            f"{entry.name:<{width}}  {entry.rows:>7,} lines  {entry.bytes:>12,}  {entry.sha256}"
        )
    if report.pictures:
        total = sum(p.bytes for p in report.pictures)
        lines.append(f"pictures/ ({len(report.pictures):,} pictures)  {total:,} bytes")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.write_pid_files",
        description="Writes the Prison Intelligence Dataset's CSV files and pictures to a folder.",
    )
    parser.add_argument("--out", required=True, type=Path, help="a folder outside the repository")
    parser.add_argument("--profile", choices=("demo", "scale"), default="demo")
    args = parser.parse_args(argv)
    if inside_repository(args.out):
        print(
            f"refusing {args.out}: it is inside the repository's working tree, and the generated "
            "files are never committed. Give a folder outside it.",
            file=sys.stderr,
        )
        return 2
    plan = pid_plan.build_plan(args.profile)
    report = pid_files.write_files(plan, args.out)
    if report.pictures:
        write_contact_sheet(plan, args.out)
    print(_table(report))
    print(f"manifest: {args.out / pid_files.MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
