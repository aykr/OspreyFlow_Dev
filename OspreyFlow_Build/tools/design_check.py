"""`make design-check` — the design detector over the Glass, against `DESIGN.md` (ADR-115, E1).

Runs `impeccable detect` (Apache-2.0, pinned in Core's `package.json` so it runs offline) over the
Glass's source and fails, naming each, on any finding `DESIGN.md` §9 does not list as a documented
exception. Advisory findings count too: §10's copy rules (no em-dash register, for one) are the
contract's, not the detector's suggestions. Also fails when Core's `DESIGN.md` — the copy the
detector reads, beside the code it checks — differs from the contract in `spec/design/`.

§9's exceptions that the detector reports, and how each is recognised:
- exception 4, the measurement grid on the graph canvas only: `codex-grid-background` inside the
  `.network-canvas` rule, and nowhere else.

Non-vacuous: `tests/test_design_check.py` runs the real detector over a planted status stripe, and
over the canvas grid beside the same grid on another surface.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.layout import CORE, REPO

DESIGN_SOURCE = REPO / "OspreyFlow_Build" / "spec" / "design" / "DESIGN.md"
SCANNED = [CORE / "apps" / "workspace" / "src"]

#: (antipattern, the CSS rule it is excused in) — DESIGN.md §9.
EXCEPTIONS = {("codex-grid-background", ".network-canvas")}


def detect(paths: list[Path]) -> list[dict[str, Any]]:
    """The detector's findings, as it reports them. It exits non-zero when it finds anything."""
    completed = subprocess.run(  # noqa: S603
        ["npx", "--no-install", "impeccable", "detect", "--json", *map(str, paths)],  # noqa: S607
        cwd=CORE,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in (0, 2) or not completed.stdout.strip().startswith("["):
        raise RuntimeError(f"impeccable detect did not run: {completed.stderr.strip()[:400]}")
    findings: list[dict[str, Any]] = json.loads(completed.stdout)
    return findings


def enclosing_selector(path: Path, line: int) -> str:
    """The selector of the CSS rule a 1-based line falls in."""
    lines = path.read_text(encoding="utf-8").splitlines()[:line]
    for text in reversed(lines):
        if "{" in text:
            return text.split("{", 1)[0].strip()
    return ""


def unexcused(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        f
        for f in findings
        if (f["antipattern"], enclosing_selector(Path(f["file"]), int(f["line"]))) not in EXCEPTIONS
    ]


def copy_drift(core_copy: str, source: Path = DESIGN_SOURCE) -> bool:
    return core_copy != source.read_text(encoding="utf-8")


def main() -> int:
    failed = False
    if copy_drift((CORE / "DESIGN.md").read_text(encoding="utf-8")):
        print("design-check: OspreyFlow_Core/DESIGN.md differs from spec/design/DESIGN.md")
        failed = True
    for f in unexcused(detect(SCANNED)):
        where = Path(f["file"]).relative_to(CORE)
        found = f"{f['antipattern']} ({f['severity']})"
        print(f"design-check: {where}:{f['line']} {found}: {f['snippet']}")
        failed = True
    if not failed:
        print("design-check: no finding outside DESIGN.md §9, and Core's DESIGN.md is the contract")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
