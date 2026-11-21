"""`make design-check` — the design detector over the Glass, against `DESIGN.md` (ADR-115, E1).

Runs `impeccable detect` (Apache-2.0, pinned in Core's `package.json` so it runs offline) over the
Glass's source and fails, naming each, on any finding `DESIGN.md` §9 does not list as a documented
exception. Advisory findings count too: §10's copy rules (no em-dash register, for one) are the
contract's, not the detector's suggestions. Also fails when Core's `DESIGN.md` — the copy the
detector reads, beside the code it checks — differs from the contract in `spec/design/`.

§9's exceptions that the detector reports, and how each is recognised:
- exception 4, the measurement grid on the graph canvas only: `codex-grid-background` inside the
  `.network-canvas` rule, and nowhere else.

Scans the Glass's source and `packages/design` (where `primitives.css` is since ADR-152 decision 6;
`tests/glass_trees/test_design_gates_reach.py` holds the reach), and the pages service's
`tree-default`, `modules` and `server/views`, whose `.njk` templates the detector cannot read as
they are (`detect` hands it each as an `.html` copy; `tests/glass_trees/test_pages_foundation.py`
plants a side stripe in a template and shows it found).

Non-vacuous: `tests/test_design_check.py` runs the real detector over a planted status stripe, and
over the canvas grid beside the same grid on another surface.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from tools.layout import CORE, PAGES_COPY_ROOTS, REPO

#: Where `impeccable` is installed (Core's `node_modules`): the detector runs from here, whatever
#: folder a caller's `CORE` names.
DETECTOR_DIR = CORE
DESIGN_SOURCE = REPO / "OspreyFlow_Build" / "spec" / "design" / "DESIGN.md"
#: The Glass's source, and the design package (ADR-152 decision 6) where `primitives.css` (which
#: holds the one documented exception), `scale.css` and `panelType.css` live.
#: `tests/glass_trees/test_design_gates_reach.py` holds the reach. The shared package's source
#: (PL4 slice C) is read too: what moved out of the Glass's folder is still read.
SCANNED = [
    CORE / "apps" / "workspace" / "src",
    CORE / "packages" / "design",
    CORE / "packages" / "glass-shared" / "src",
    # The pages service's templates and modules (slice IS5a0). A folder that is not there yet is
    # not run.
    *(CORE / name for name in PAGES_COPY_ROOTS),
]

#: (antipattern, the CSS rule it is excused in) — DESIGN.md §9.
EXCEPTIONS = {("codex-grid-background", ".network-canvas")}


def _run(paths: list[Path]) -> list[dict[str, Any]]:
    completed = subprocess.run(  # noqa: S603
        ["npx", "--no-install", "impeccable", "detect", "--json", *map(str, paths)],  # noqa: S607
        cwd=DETECTOR_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in (0, 2) or not completed.stdout.strip().startswith("["):
        raise RuntimeError(f"impeccable detect did not run: {completed.stderr.strip()[:400]}")
    findings: list[dict[str, Any]] = json.loads(completed.stdout)
    return findings


def _templates(paths: list[Path]) -> list[Path]:
    """The Nunjucks templates under the paths: a `.njk` file is HTML with tags the detector does
    not read as a page."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found += sorted(path.rglob("*.njk"))
        elif path.suffix == ".njk":
            found.append(path)
    return found


def detect(paths: list[Path]) -> list[dict[str, Any]]:
    """The detector's findings, as it reports them. It exits non-zero when it finds anything.

    `impeccable` reads HTML, CSS and scripts, and not `.njk`. A template is HTML with `{% %}` tags
    in it, so each one under the paths is handed to the detector as a copy named `.html`, and the
    template's own path is put back on what it finds (the copies sit in folders numbered by
    template, so a finding is matched to its template by the folder, not the name). A path that is
    not there (a pages folder with nothing in it yet) is not run."""
    existing = [Path(p) for p in paths if Path(p).exists()]
    findings = _run(existing) if existing else []
    templates = _templates(existing)
    if templates:
        with tempfile.TemporaryDirectory() as tmp:
            for index, template in enumerate(templates):
                copy = Path(tmp) / str(index) / f"{template.name}.html"
                copy.parent.mkdir()
                copy.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            for finding in _run([Path(tmp)]):
                index = int(Path(finding["file"]).parent.name)
                findings.append({**finding, "file": str(templates[index])})
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
