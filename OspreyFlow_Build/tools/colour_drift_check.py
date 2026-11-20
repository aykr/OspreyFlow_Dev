"""`python -m tools.colour_drift_check` — no colour in the Glass that DESIGN.md does not hold.

`06_DECISIONS.md` ADR-097: `spec/design/DESIGN.md` is the design contract ("anything on a screen
that is not in this file is drift"), and the design review that adopted it asked for a detector
(`npx impeccable detect`) this repository does not have. This is that detector, for colour: every
hex, `rgb()`/`rgba()` and `hsl()`/`hsla()` literal in the Glass's own source must be one DESIGN.md
holds. Two kinds of file are exempt, by name: a declared mirror of the tokens (the WebGL canvas
cannot read CSS custom properties, so `color/tokens.ts` and `color/palette.ts` restate them, and
their own tests hold them to `tokens.css`), and `tokens.css` itself (in `packages/design` since
ADR-152: that folder is walked too, so its neighbours stay held to the palette). Drift already in
the Glass when this gate was built is listed in `tests/fixtures/colour_drift_allowlist.txt`, each
with its reason, until it is fixed; a new literal anywhere else fails.

Non-vacuous: `tests/test_colour_drift_check.py` plants literals in the shapes the real code uses
(a hex in a style object, an `rgba` canvas fill, a fallback inside `var(...)`) and asserts each is
reported.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from tools.layout import CORE, REPO

GLASS_SRC = CORE / "apps" / "workspace" / "src"
#: The design tokens' own folder (ADR-152 decision 6); `tokens.css` is exempt in it by name.
DESIGN_PACKAGE = CORE / "packages" / "design"
#: The shared package's source (ADR-152 decision 6): the plain leaves and stores that moved out of
#: the Glass's own folder (PL4 slice C), so the check must read them where they are now.
SHARED_SRC = CORE / "packages" / "glass-shared" / "src"
DESIGN_PATH = REPO / "OspreyFlow_Build" / "spec" / "design" / "DESIGN.md"
ALLOWLIST_PATH = REPO / "OspreyFlow_Build" / "tests" / "fixtures" / "colour_drift_allowlist.txt"

#: Files that restate the tokens for the canvas, held to `tokens.css` by their own tests.
MIRRORS = frozenset({"color/tokens.ts", "color/palette.ts"})
#: The tokens themselves, by name relative to `DESIGN_PACKAGE`.
TOKENS_FILES = frozenset({"tokens.css"})
#: Each folder the check walks, with the files in it exempt by name. The count of files scanned in
#: them (`scanned_count`) is said on every run and held not to fall by
#: `tests/glass_trees/test_design_tokens_location.py` and `test_glass_shared_leaves.py`.
SCANNED: tuple[tuple[Path, frozenset[str]], ...] = (
    (GLASS_SRC, MIRRORS),
    (DESIGN_PACKAGE, TOKENS_FILES),
    (SHARED_SRC, frozenset()),
)

_HEX = re.compile(r"(?<![&\w])#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z])")
_FUNCTION = re.compile(r"\b(?:rgba?|hsla?)\(\s*[0-9.,%\s/]+\)")


def _normal(literal: str) -> str:
    literal = literal.lower()
    if re.fullmatch(r"#[0-9a-f]{3}", literal):
        return "#" + "".join(c * 2 for c in literal[1:])
    return re.sub(r"\s+", "", literal)


def palette_from(design_text: str) -> frozenset[str]:
    """Every colour DESIGN.md names, normalised."""
    found = _HEX.findall(design_text) + _FUNCTION.findall(design_text)
    return frozenset(_normal(c) for c in found)


def scanned_files(root: Path, mirrors: frozenset[str]) -> list[Path]:
    """The files `find_drift` reads under `root`: styles and sources, no tests, no exempt file."""
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.suffix in {".ts", ".tsx", ".css"}
        and ".test." not in path.name
        and path.relative_to(root).as_posix() not in mirrors
    ]


def scanned_count(scanned: tuple[tuple[Path, frozenset[str]], ...] | None = None) -> int:
    return sum(len(scanned_files(root, mirrors)) for root, mirrors in (scanned or SCANNED))


def find_drift(
    root: Path,
    palette: frozenset[str],
    *,
    mirrors: frozenset[str] = MIRRORS,
    allowed: set[tuple[str, str]] | None = None,
) -> list[tuple[str, int, str]]:
    """`(path, line, literal)` for each colour under `root` not on the palette, sorted."""
    allowed = allowed or set()
    drift: list[tuple[str, int, str]] = []
    for path in scanned_files(root, mirrors):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for literal in _HEX.findall(line) + _FUNCTION.findall(line):
                if _normal(literal) in palette or (rel, _normal(literal)) in allowed:
                    continue
                drift.append((rel, number, literal))
    return drift


def stale_allowlist(
    root: Path, palette: frozenset[str], allowed: set[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Allowlist entries that excuse nothing now: the file no longer holds the literal, or the
    literal is on the palette. A stale entry would let the literal back in without a word."""
    stale: list[tuple[str, str]] = []
    for rel, literal in sorted(allowed):
        path = root / rel
        found = (
            path.exists()
            and literal not in palette
            and any(
                _normal(c) == literal
                for line in path.read_text(encoding="utf-8").splitlines()
                for c in _HEX.findall(line) + _FUNCTION.findall(line)
            )
        )
        if not found:
            stale.append((rel, literal))
    return stale


def _load_allowlist() -> set[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set()
    if not ALLOWLIST_PATH.exists():
        return allowed
    for raw in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip() if raw.lstrip().startswith("#") else raw.strip()
        if not line:
            continue
        path, literal = line.split("\t")[:2]
        allowed.add((path.strip(), _normal(literal.strip())))
    return allowed


def main() -> int:
    palette = palette_from(DESIGN_PATH.read_text(encoding="utf-8"))
    allowed = _load_allowlist()
    drift = []
    for root, mirrors in SCANNED:
        held = allowed if root == GLASS_SRC else None
        found = find_drift(root, palette, mirrors=mirrors, allowed=held)
        drift += found
        for path, number, literal in found:
            where = root.relative_to(CORE).as_posix()
            print(f"{where}/{path}:{number}: {literal} is not in DESIGN.md")
    stale = stale_allowlist(GLASS_SRC, palette, allowed)
    for path, literal in stale:
        print(f"{ALLOWLIST_PATH.name}: {path} {literal} excuses nothing now; remove the line")
    if drift or stale:
        print(
            f"colour-drift-check: {len(drift)} colour(s) outside DESIGN.md, {len(stale)} stale allowlist line(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"colour-drift-check: scanned {scanned_count()} files; "
        "every colour in them is one DESIGN.md holds"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
