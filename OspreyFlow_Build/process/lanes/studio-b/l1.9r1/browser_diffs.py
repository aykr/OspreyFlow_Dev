"""The diffs this lane sends rather than commits (the admin lane's form, `actionRegistry.ts`,
`every-harness.spec.ts`), applied for the keyboard and axe runs only, then the files put back as HEAD
holds them, by name (never `git checkout .`). Run from `OspreyFlow_Core`:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.9r1/browser_diffs.py apply|restore

`apply` refuses a tree with changes to tracked files, so a gate's own files are never mixed in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LANE = Path(__file__).resolve().parent.parent
TOP = LANE.parents[3]
DIFFS = [LANE / f"L1.9_{name}.diff" for name in ("admin_connections", "action_registry",
                                                    "every_harness")]  # fmt: skip


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=TOP, capture_output=True, text=True,
                          check=True).stdout  # fmt: skip


def _files() -> list[str]:
    return sorted({line.split(" b/", 1)[1] for diff in DIFFS
                   for line in diff.read_text().splitlines() if line.startswith("diff --git ")})  # fmt: skip


def main(action: str) -> int:
    if action == "apply":
        if _git("status", "--porcelain", "--untracked-files=no").strip():
            print("refused: tracked files have changes; commit or put them back first")
            return 1
        for diff in DIFFS:
            _git("apply", "--check", str(diff))
        for diff in DIFFS:
            _git("apply", str(diff))
        print("applied:", *_files(), sep="\n  ")
    elif action == "restore":
        _git("checkout", "HEAD", "--", *_files())
        left = _git("status", "--porcelain", "--untracked-files=no").strip()
        print("restored by name;", "tree clean" if not left else f"still changed:\n{left}")
        return 1 if left else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
