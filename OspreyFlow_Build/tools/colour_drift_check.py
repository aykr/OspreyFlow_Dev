"""`python -m tools.colour_drift_check` — no colour in the Glass that DESIGN.md does not hold.

`06_DECISIONS.md` ADR-097: `spec/design/DESIGN.md` is the design contract ("anything on a screen
that is not in this file is drift"), and the design review that adopted it asked for a detector
(`npx impeccable detect`) this repository does not have. This is that detector, for colour: every
hex, `rgb()`/`rgba()` and `hsl()`/`hsla()` literal in the Glass's own source must be one DESIGN.md
holds. Two kinds of file are exempt, by name: a declared mirror of the tokens (the WebGL canvas
cannot read CSS custom properties, so `color/tokens.ts` and `color/palette.ts` restate them, and
their own tests hold them to `tokens.css`), and `design/tokens.css` itself. Drift already in the
Glass when this gate was built is listed in `tests/fixtures/colour_drift_allowlist.txt`, each with
its reason, until it is fixed; a new literal anywhere else fails.

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
DESIGN_PATH = REPO / "OspreyFlow_Build" / "spec" / "design" / "DESIGN.md"
ALLOWLIST_PATH = REPO / "OspreyFlow_Build" / "tests" / "fixtures" / "colour_drift_allowlist.txt"

#: Files that restate the tokens for the canvas, held to `tokens.css` by their own tests.
MIRRORS = frozenset({"color/tokens.ts", "color/palette.ts", "design/tokens.css"})

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
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".ts", ".tsx", ".css"} or ".test." in path.name:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in mirrors or rel == "design/tokens.css":  # the tokens themselves
            continue
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
    drift = find_drift(GLASS_SRC, palette, allowed=allowed)
    for path, number, literal in drift:
        print(f"apps/workspace/src/{path}:{number}: {literal} is not in DESIGN.md")
    stale = stale_allowlist(GLASS_SRC, palette, allowed)
    for path, literal in stale:
        print(f"{ALLOWLIST_PATH.name}: {path} {literal} excuses nothing now; remove the line")
    if drift or stale:
        print(
            f"colour-drift-check: {len(drift)} colour(s) outside DESIGN.md, {len(stale)} stale allowlist line(s)",
            file=sys.stderr,
        )
        return 1
    print("colour-drift-check: every colour in the Glass is one DESIGN.md holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
