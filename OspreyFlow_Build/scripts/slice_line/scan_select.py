#!/usr/bin/env python3
"""The pure tests that scan the files a slice touches (README, "The scans a slice's checks include").

AD2 (18 November 2026): its checks named the form's own tests, and `test_admin_sections.py`, which walks the
workspace's sources and counts the routes each Admin section reads, was nobody's; the Stop hook and the verifier both
missed what the full gate caught at merge, seven minutes in. So the line, not the conductor, decides which whole-tree
scanners a slice's checks include: `scan_map.tsv` (beside this file, in the line's own folder, which neither the
conductor nor any slice can change) maps each pure test that walks the repository to the path prefixes it walks.
For the paths a slice's branch changes, every mapped test whose prefixes they fall under runs, in the Stop hook and on
the merge result. Only pure tests (the live ones are `make test`'s `--ignore` list), and only those mapped to touched
paths, bound the cost.

The map is shown complete by `unmapped()`: every pure test whose source, or a `tools/` module or test helper it
imports, walks a folder (rglob, os.walk, a `**` glob, `git ls-files`) has a row, either with the prefixes it walks or
with `-` and why it walks only its own temporary folder. A new walker without a row fails the line's suite.

Standard library only, Python 3.9: the Stop hook loads it from the installed folder.

    scan_select.py <tree> <base>     print the selected tests (relative to OspreyFlow_Build), one a line
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

MAP = Path(__file__).resolve().parent / "scan_map.tsv"
WALK = re.compile(r"\.rglob\(|os\.walk\(|\.glob\(\s*f?[\"'][^\"']*\*\*|\biglob\(|ls-files")
IMPORT = re.compile(r"^\s*(?:from\s+((?:tools|tests)(?:\.\w+)+)\s+import|import\s+((?:tools|tests)(?:\.\w+)+))", re.M)
RUN_M = re.compile(r"[\"'](?:-m)[\"'],\s*[\"']((?:tools)\.\w+)[\"']|-m\s+((?:tools)\.\w+)")
Entry = Tuple[str, Tuple[str, ...], str]


def load(text: str) -> List[Entry]:
    out = []
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) < 3:
            raise ValueError("scan_map.tsv: a row needs a test, its prefixes (or -) and why: " + ln)
        prefixes = () if parts[1].strip() == "-" else tuple(p.strip() for p in parts[1].split(",") if p.strip())
        out.append((parts[0].strip(), prefixes, parts[2].strip()))
    return out


def entries(path: Path = MAP) -> List[Entry]:
    return load(path.read_text())


def select(touched: List[str], table: List[Entry]) -> List[str]:
    return sorted({t for t, prefixes, _ in table if any(p.startswith(prefixes) for p in touched)} if touched else set())


def touched(tree: str, base: str) -> List[str]:
    p = subprocess.run(["git", "diff", "--name-only", "--no-renames", base, "HEAD"], cwd=tree, capture_output=True,
                       text=True)
    if p.returncode != 0:
        raise RuntimeError("git diff against the slice's base failed: " + p.stderr.strip())
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def command(tree: str, tests: List[str], python: str = "") -> str:
    """How the selected tests run, from the tree's root: pure (closed ports), on the tree's own environment (or the
    `python` the caller's environment gives, as the merge script's CI-built one does)."""
    venv = Path(tree) / "OspreyFlow_Core/.venv/bin/python"
    py = python or (str(venv) if venv.is_file() else "uv run --frozen python")
    files = " ".join("../OspreyFlow_Build/" + t for t in tests)
    return (f"cd OspreyFlow_Core && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 {py} -m pytest -c ../OspreyFlow_Build/pytest.ini "
            f"-q -p no:cacheprovider {files}")


def not_named(tests: List[str], *commands: str) -> List[str]:
    """The selected tests the slice's own commands do not already run (by file name)."""
    text = " ".join(commands)
    return [t for t in tests if t.split("/")[-1] not in text]


# ------------------------------------------------------------------ completeness


def live_set(build: Path) -> List[str]:
    text = (build / "Makefile").read_text()
    return sorted(set(re.findall(r"--ignore=\.\./OspreyFlow_Build/(\S+)", text)))


def is_live(rel: str, live: List[str]) -> bool:
    return any(rel == ln or rel.startswith(ln.rstrip("/") + "/") for ln in live)


def walks(build: Path, path: Path, seen: Dict[Path, bool], depth: int = 0) -> bool:
    """Whether this file walks a folder, itself or through a tools/ module or test helper it imports or runs."""
    if path in seen:
        return seen[path]
    seen[path] = False
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return False
    hit = bool(WALK.search(text))
    if not hit and depth < 3:
        mods = [a or b for a, b in IMPORT.findall(text)] + [a or b for a, b in RUN_M.findall(text)]
        for m in mods:
            f = build / (m.replace(".", "/") + ".py")
            if f.is_file() and walks(build, f, seen, depth + 1):
                hit = True
                break
    seen[path] = hit
    return hit


def unmapped(build: Path, table: List[Entry], only: Optional[Set[str]] = None) -> List[str]:
    """Pure tests that walk a folder and have no row in the map (of `only`, when given: the merge's own check)."""
    named = {t for t, _, _ in table}
    live = live_set(build)
    seen: Dict[Path, bool] = {}
    out = []
    for f in sorted((build / "tests").rglob("test_*.py")):
        rel = f.relative_to(build).as_posix()
        if is_live(rel, live) or rel in named or (only is not None and rel not in only):
            continue
        if walks(build, f, seen):
            out.append(rel)
    return out


def stale(build: Path, table: List[Entry]) -> List[str]:
    """Rows naming a test that is not there, or a prefix that names nothing in the repository."""
    root = build.parent
    out = [f"{t}: no such test" for t, _, _ in table if not (build / t).is_file()]
    for t, prefixes, _ in table:
        for p in prefixes:
            if not (root / p).exists():
                out.append(f"{t}: {p} names nothing")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: scan_select.py <tree> <base>")
    for t in select(touched(sys.argv[1], sys.argv[2]), entries()):
        print(t)
