"""`make design-check` (ADR-115, Phase E stage E1): the design detector the handoff names
(`npx impeccable detect`) run over the Glass, failing on any finding `DESIGN.md` §9 does not list as a
documented exception; and Core's own `DESIGN.md` (the copy the detector reads) held equal to the
source in `spec/design/`.

What a mistake would do, and the case that catches it:
- a finding passed because the filter matched nothing — `test_a_status_stripe_is_reported`, which
  runs the real detector over a planted stripe in the shape the old toast had;
- the canvas grid (§9 exception 4) reported, or a grid in another file excused with it —
  `test_the_canvas_grid_is_the_one_excused_grid` (the detector reports one grid per file, at the
  first; a second grid inside `primitives.css` is `canvasGrid.test.ts`'s to catch);
- Core's copy drifting from the contract — `test_cores_design_md_is_the_contract`.
"""

from __future__ import annotations

from pathlib import Path

from tools import design_check
from tools.layout import CORE, REPO


def test_cores_design_md_is_the_contract() -> None:
    source = REPO / "OspreyFlow_Build" / "spec" / "design" / "DESIGN.md"
    assert (CORE / "DESIGN.md").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert design_check.copy_drift(source.read_text(encoding="utf-8") + "\nmore\n", source) is True


def test_a_status_stripe_is_reported(tmp_path: Path) -> None:
    # The shape the old toast had (primitives.css before E1): the detector reports a side stripe only
    # on a card-like rule, and a bare `border-left` it passes.
    planted = tmp_path / "planted.css"
    planted.write_text(
        ".toast {\n  background: var(--surface-raised); box-shadow: var(--overlay-shadow);\n"
        "  border-radius: var(--r-overlay); padding: var(--sp-8) var(--sp-12);\n}\n"
        ".toast--error { border-left: 3px solid var(--error); }\n",
        encoding="utf-8",
    )
    findings = design_check.detect([planted])
    assert [f["antipattern"] for f in design_check.unexcused(findings)] == ["side-tab"]


GRID = (
    "  background-color: var(--surface-sunken);\n"
    "  background-image:\n"
    "    linear-gradient(var(--grid-line) 1px, transparent 1px),\n"
    "    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);\n"
    "  background-size: 16px 16px;\n"
)


def test_the_canvas_grid_is_the_one_excused_grid(tmp_path: Path) -> None:
    canvas = tmp_path / "primitives.css"
    canvas.write_text(f".network-canvas {{\n{GRID}}}\n", encoding="utf-8")
    elsewhere = tmp_path / "other.css"
    elsewhere.write_text(f".panel {{\n{GRID}}}\n", encoding="utf-8")
    findings = design_check.detect([canvas, elsewhere])
    assert sorted(Path(f["file"]).name for f in findings if f["antipattern"] == "codex-grid-background") == [
        "other.css",
        "primitives.css",
    ]
    assert [Path(f["file"]).name for f in design_check.unexcused(findings)] == ["other.css"]
