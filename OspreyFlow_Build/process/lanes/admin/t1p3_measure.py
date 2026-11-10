"""T1 part 3's measurement: what `tools/live_select.py` selects for each of main's last N lane merges, from that merge's
own diff (its first parent to the merge), with the map and the live set as they are in this checkout. Run from
OspreyFlow_Build as `../OspreyFlow_Core/.venv/bin/python process/lanes/admin/t1p3_measure.py [N]`; it prints one line
a merge (its hash, the count, the merge's subject) and the mean, and is the only source of the record's figure."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools import live_select  # noqa: E402


def main(n: int = 18) -> None:
    repo = live_select.Repo()
    live = repo.live_set()
    merges = subprocess.run(["git", "log", "--merges", "--format=%h %s", "-200", "main"],
                            capture_output=True, text=True, check=True).stdout.splitlines()
    rows = []
    for line in merges:
        h, subject = line.split(" ", 1)
        if not subject.startswith("merge(lane/"):
            continue
        changed = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{h}^1", h],
                                 capture_output=True, text=True, check=True).stdout.split()
        rows.append((h, len(live_select.select(changed, repo)), subject))
        if len(rows) == n:
            break
    for h, k, subject in rows:
        print(f"{h}  {k:4d}/{len(live)}  {subject[:90]}")
    total = sum(k for _, k, _ in rows)
    print(f"mean {total / len(rows):.1f} of {len(live)} ({100 * total / len(rows) / len(live):.0f}%) over {len(rows)} lane merges")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 18)
