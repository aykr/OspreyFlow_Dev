"""Two tracked files must never differ only in case.

Found 4 October 2026: `apps/workspace/src/inspector/LinkHistory.tsx` (a component) and
`apps/workspace/src/inspector/linkHistory.ts` (a pure helper) sat side by side for a day. On the
case-sensitive disk of the build machines they were two files; on the owner's Mac, whose disk is
case-insensitive, `./LinkHistory` resolved to whichever matched first, the component import came
back undefined, six unit cases failed and `tsc` refused the pair (TS1149). Nothing in CI could see
it, because CI runs on Linux. This check makes Linux fail the way a Mac does: it lists every pair
of tracked paths whose lower-cased forms are equal, and every pair of script modules in one folder
whose stems are equal ignoring case (a bare import resolves by stem, whatever the extension).

Run as `PYTHONPATH=../OspreyFlow_Build python -m tools.case_collision_check` from
`OspreyFlow_Core`; exits 1 and names each pair. `tests/test_case_collision_check.py` plants a pair
against the pure function (the proof `CLAUDE.md` rule 15 asks for) and runs it over the real tree.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable

from tools.layout import ROOT

#: The extensions a bare `./Name` import may resolve to, in TypeScript and Vite alike. Two files in
#: one folder whose stems differ only in case collide as *modules* even when their extensions differ
#: (`LinkHistory.tsx` against `linkHistory.ts` is the shape that was found), so for these the
#: comparison drops the extension. Every other file compares as its whole path.
MODULE_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"})


def _keys(path: str) -> list[str]:
    lowered = path.lower()
    keys = [lowered]
    stem, dot, ext = lowered.rpartition(".")
    if dot and f".{ext}" in MODULE_EXTENSIONS:
        keys.append(f"{stem}#module")
    return keys


def case_collisions(paths: Iterable[str]) -> list[tuple[str, str]]:
    """Every pair of paths that would collide on a case-insensitive disk or in a bare module import,
    each pair in the order the paths were given. A pair is reported once."""
    seen: dict[str, str] = {}
    pairs: list[tuple[str, str]] = []
    reported: set[tuple[str, str]] = set()
    for path in paths:
        for key in _keys(path):
            earlier = seen.get(key)
            if earlier is None:
                seen[key] = path
            elif earlier != path and (earlier, path) not in reported:
                reported.add((earlier, path))
                pairs.append((earlier, path))
    return pairs


def tracked_paths() -> list[str]:
    """Every path git tracks in this repository, relative to its root."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return [p for p in out.split("\0") if p]


def main() -> int:
    pairs = case_collisions(tracked_paths())
    for a, b in pairs:
        print(f"case-collision-check: {a} and {b} differ only in case", file=sys.stderr)
    if pairs:
        print(f"case-collision-check: {len(pairs)} pair(s)", file=sys.stderr)
        return 1
    print("case-collision-check: no two tracked files differ only in case")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
