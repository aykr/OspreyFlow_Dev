"""The `make ci` gates that read the Glass's styles still read `primitives.css`, `scale.css` and `panelType.css` now
they live in `packages/design` (ADR-152 decision 6; slice PL4b2, round 2; the owner's ruling of 20 November 2026 that a
move must not silently lower a check's reach).

Three gates walked `apps/workspace/src` and so read the three files while they were there; the colour-drift check was
extended in PL4b (`test_design_css_location.py` holds it). This file holds the other three, each by a plant at the
shape the gate really sees:

* `make design-check`'s detector (`tools/design_check.py`): `test_the_design_detector_reads_packages_design`. Its one
  documented exception (DESIGN.md section 9, exception 4, the measurement grid on `.network-canvas`) lives in
  `primitives.css`, so a detector that no longer read the file would excuse a rule it never saw;
* `tools/ui_words_check.py` (the banned phrase in a CSS `content:` string): `test_the_ui_words_check_reads_packages_design`;
* `tools/no_branches_check.py` (CSS is among its suffixes): `test_the_no_branches_check_reads_packages_design`.

Each plant is a file written into the real `packages/design` folder for the length of the test and removed after it, so
the gate is run over the real roots it is configured with, not over roots the test chose. `test_each_gate_s_roots_hold_
the_three_files` shows the three files are inside the roots of all three, by name.

This file walks no part of the repository by `git ls-files`: it reads `OspreyFlow_Core/packages/design/` only.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tools import design_check, no_branches_check, ui_words_check
from tools.layout import CORE

DESIGN = CORE / "packages" / "design"
THE_THREE = ("primitives.css", "scale.css", "panelType.css")
PLANT = "zz_planted_gate_reach.css"


@pytest.fixture
def planted() -> Iterator[Path]:
    """The path in the real `packages/design` a test writes its plant to; gone after the test."""
    path = DESIGN / PLANT
    assert not path.exists()
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _under(path: Path, roots: list[Path]) -> bool:
    return any(root == path or root in path.parents for root in roots)


def test_each_gate_s_roots_hold_the_three_files() -> None:
    detector = [Path(p) for p in design_check.SCANNED]
    words = [ui_words_check.GLASS_SRC, ui_words_check.DESIGN_PACKAGE]
    branches = [CORE / top for top in no_branches_check.SCANNED]
    for name in THE_THREE:
        assert (DESIGN / name).is_file(), f"{name} is not in packages/design"
        for gate, roots in (("design_check", detector), ("ui_words_check", words), ("no_branches_check", branches)):
            assert _under(DESIGN / name, roots), f"{gate} does not read packages/design/{name}"


def test_the_design_detector_reads_packages_design(planted: Path) -> None:
    # The shape the old toast had: a side stripe on a card-like rule, which the detector reports.
    planted.write_text(
        ".planted {\n  background: var(--surface-raised); box-shadow: var(--overlay-shadow);\n"
        "  border-radius: var(--r-overlay); padding: var(--sp-8) var(--sp-12);\n}\n"
        ".planted--error { border-left: 3px solid var(--error); }\n",
        encoding="utf-8",
    )
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [(PLANT, "side-tab")]


def test_the_design_detector_still_excuses_the_canvas_grid_in_primitives_css() -> None:
    # The real call site: `main()` over the real roots, the one documented exception in a file now in the new folder.
    assert design_check.unexcused(design_check.detect([DESIGN / "primitives.css"])) == []
    assert design_check.main() == 0


def test_the_ui_words_check_reads_packages_design(planted: Path, capsys: pytest.CaptureFixture[str]) -> None:
    planted.write_text('.planted::after {\n  content: "Target model";\n}\n', encoding="utf-8")
    assert ui_words_check.main() == 1
    assert f"packages/design/{PLANT}:2:" in capsys.readouterr().out


def test_the_no_branches_check_reads_packages_design(planted: Path, capsys: pytest.CaptureFixture[str]) -> None:
    planted.write_text('.planted::after {\n  content: "Branch to a new case";\n}\n', encoding="utf-8")
    assert no_branches_check.main() == 1
    assert f"packages/design/{PLANT}:2:" in capsys.readouterr().out
