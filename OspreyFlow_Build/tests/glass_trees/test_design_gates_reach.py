"""The `make ci` gates that read the Glass's styles still read `primitives.css`, `scale.css` and
`panelType.css` now they live in `packages/design` (ADR-152 decision 6; slice PL4b2, round 2; the
owner's ruling of 20 November 2026 that a move must not silently lower a check's reach).

Four gates walked `apps/workspace/src` and so read the three files while they were there. The
colour-drift check was extended in PL4b (`test_design_css_location.py` holds it). This file holds
the other three, each by a plant at the shape the gate really sees:

* `make design-check`'s detector (`tools/design_check.py`):
  `test_the_design_detector_reads_packages_design`. Its one documented exception (DESIGN.md
  section 9, exception 4, the measurement grid on `.network-canvas`) lives in `primitives.css`, so
  a detector that no longer read the file would excuse a rule it never saw;
* `tools/ui_words_check.py` (the banned phrase in a CSS `content:` string):
  `test_the_ui_words_check_reads_packages_design`;
* `tools/no_branches_check.py` (CSS is among its suffixes):
  `test_the_no_branches_check_reads_packages_design`.

Each plant is a file written into a temporary copy of `packages/design`, and the gate's roots are
pointed at the copy for the length of the test. Nothing is ever written into the real folder: `make
test` runs the tests on several workers, and a plant in the real folder was seen by every reader of
it on another worker (the no-branches and ui-words tests, the colour-drift count) for as long as it
lived. The roots the gates are really configured with are not lost by that:
`test_each_gate_s_roots_hold_the_three_files` shows the three files are inside the real roots of all
three, by name, and the plants are written in the real files' own folder layout.

**The pages roots (slices IS5a0 and GR2a).** `apps/pages/tree-default`, `apps/pages/tree-govuk`, `apps/pages/modules` and
`apps/pages/server/views` hold the Default tree's templates, the GOV.UK tree's, and the client modules. The same four gates read them, and so does the copy walker of
`tests/test_copy_says_no_client.py`: `test_each_gate_names_the_pages_roots` holds each gate's own list to the names
`tools.layout.PAGES_COPY_ROOTS` gives, so a gate that drops one is red; `tests/glass_trees/test_pages_foundation.py`
holds that each gate reads a violation planted under each root, `tree-govuk` among them (a colour outside the tokens, an inline
side stripe, a branch word and a banned word, each flagged by the gate that owns it).

This file walks no part of the repository by `git ls-files`: it reads
`OspreyFlow_Core/packages/design/` only (copied, never written).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from tools import design_check, no_branches_check, ui_words_check
from tools.layout import CORE

DESIGN = CORE / "packages" / "design"
THE_THREE = ("primitives.css", "scale.css", "panelType.css")
PLANT = "zz_planted_gate_reach.css"


@pytest.fixture
def planted(tmp_path: Path) -> Path:
    """The path of a plant in a temporary copy of `packages/design`; the real folder is not written.

    The copy sits at `<tmp>/packages/design`, the layout the gates print their paths from.
    """
    copy = tmp_path / "packages" / "design"
    shutil.copytree(DESIGN, copy, ignore=shutil.ignore_patterns("node_modules"))
    return copy / PLANT


def _under(path: Path, roots: list[Path]) -> bool:
    return any(root == path or root in path.parents for root in roots)


def test_each_gate_s_roots_hold_the_three_files() -> None:
    gates = {
        "design_check": [Path(p) for p in design_check.SCANNED],
        "ui_words_check": [ui_words_check.GLASS_SRC, ui_words_check.DESIGN_PACKAGE],
        "no_branches_check": [CORE / top for top in no_branches_check.SCANNED],
    }
    for name in THE_THREE:
        assert (DESIGN / name).is_file(), f"{name} is not in packages/design"
        for gate, roots in gates.items():
            assert _under(DESIGN / name, roots), f"{gate} does not read packages/design/{name}"


def test_the_design_detector_reads_packages_design(
    planted: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The shape the old toast had: a side stripe on a card-like rule, which the detector reports.
    planted.write_text(
        ".planted {\n  background: var(--surface-raised); box-shadow: var(--overlay-shadow);\n"
        "  border-radius: var(--r-overlay); padding: var(--sp-8) var(--sp-12);\n}\n"
        ".planted--error { border-left: 3px solid var(--error); }\n",
        encoding="utf-8",
    )
    # The gate's own SCANNED, its package root pointed at the copy: the call is `detect(SCANNED)`.
    monkeypatch.setattr(design_check, "SCANNED", [planted.parent])
    found = design_check.unexcused(design_check.detect(design_check.SCANNED))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [(PLANT, "side-tab")]


def test_the_design_detector_still_excuses_the_canvas_grid_in_primitives_css() -> None:
    # The real call site: the one documented exception, in a file that is now in the new folder.
    assert design_check.unexcused(design_check.detect([DESIGN / "primitives.css"])) == []
    assert design_check.main() == 0


def test_the_ui_words_check_reads_packages_design(
    planted: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui_words_check, "DESIGN_PACKAGE", planted.parent)
    monkeypatch.setattr(ui_words_check, "GLASS_SRC", planted.parent.parent / "no-src")
    planted.write_text('.planted::after {\n  content: "Target model";\n}\n', encoding="utf-8")
    assert ui_words_check.main() == 1
    assert f"packages/design/{PLANT}:2:" in capsys.readouterr().out


def test_the_no_branches_check_reads_packages_design(
    planted: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # `tree_files` binds its defaults at definition: the gate's walk is replaced, not a constant.
    walk: Callable[..., dict[str, str]] = no_branches_check.tree_files
    tmp_core = planted.parent.parent.parent
    monkeypatch.setattr(
        no_branches_check, "tree_files", lambda: walk(tmp_core, ("packages/design",))
    )
    planted.write_text('.planted::after {\n  content: "Branch to a case";\n}\n', encoding="utf-8")
    assert no_branches_check.main() == 1
    assert f"packages/design/{PLANT}:2:" in capsys.readouterr().out


PAGES_ROOTS = (
    "apps/pages/tree-default",
    "apps/pages/tree-govuk",
    "apps/pages/modules",
    "apps/pages/server/views",
)


def test_each_gate_names_the_pages_roots() -> None:
    """A gate's reach cannot fall below the roots now named: each gate's own list holds every root, by name."""
    from tools import colour_drift_check, layout

    from tests.test_copy_says_no_client import PAGES_COPY_ROOTS

    assert tuple(layout.PAGES_COPY_ROOTS) == PAGES_ROOTS
    assert tuple(PAGES_COPY_ROOTS) == PAGES_ROOTS
    named = {
        "design_check": {Path(p).relative_to(CORE).as_posix() for p in design_check.SCANNED},
        "ui_words_check": {p.relative_to(CORE).as_posix() for p in ui_words_check.PAGES_ROOTS},
        "colour_drift_check": {root.relative_to(CORE).as_posix() for root, _ in colour_drift_check.SCANNED},
        "no_branches_check": set(no_branches_check.SCANNED),
    }
    for gate, roots in named.items():
        assert set(PAGES_ROOTS) <= roots, f"{gate} does not read {sorted(set(PAGES_ROOTS) - roots)}"



# --- the GOV.UK tree (slice GR2a): a violation planted in a file of `tree-govuk` is flagged by the gate that owns it ------
#
# Each plant is a template written into a temporary copy of the real `apps/pages/tree-govuk`, and the gate is given the roots *it
# is itself configured with* (its own `SCANNED` or `PAGES_ROOTS`, moved under the copy), so a gate whose list left `tree-govuk`
# out reads nothing of the plant and the case is red. Nothing is written into the real folder (`make test` runs on several
# workers). The plants have the shape a template of that tree really has: a page that extends the tree's layout.

GOVUK_ROOT = "apps/pages/tree-govuk"
PLANTED_TEMPLATE = "zz_planted_gate_reach.njk"


@pytest.fixture
def govuk_core(tmp_path: Path) -> Path:
    """A temporary `OspreyFlow_Core` holding a copy of the real `tree-govuk` and the other pages roots, empty."""
    core = tmp_path / "OspreyFlow_Core"
    for root in PAGES_ROOTS:
        (core / root).mkdir(parents=True)
    shutil.copytree(CORE / GOVUK_ROOT, core / GOVUK_ROOT, dirs_exist_ok=True)
    return core


def _page(body: str) -> str:
    return '{% extends "layout.njk" %}\n{% block content %}\n' + body + "{% endblock %}\n"


def _moved(path: Path, core: Path) -> Path:
    return core / Path(path).relative_to(CORE)


def test_the_govuk_tree_is_in_the_real_copy_the_plants_are_written_in(govuk_core: Path) -> None:
    assert (govuk_core / GOVUK_ROOT / "layout.njk").is_file()
    assert (CORE / GOVUK_ROOT / "layout.njk").is_file()


def test_a_banned_word_in_the_govuk_tree_is_flagged_by_the_words_check(
    govuk_core: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = tuple(_moved(p, govuk_core) for p in ui_words_check.PAGES_ROOTS)
    monkeypatch.setattr(ui_words_check, "PAGES_ROOTS", roots)
    for name in ("GLASS_SRC", "DESIGN_PACKAGE", "SHARED_SRC"):
        monkeypatch.setattr(ui_words_check, name, govuk_core / "none")
    assert ui_words_check.main() == 0, "the real tree-govuk is not clean"
    capsys.readouterr()
    (govuk_core / GOVUK_ROOT / PLANTED_TEMPLATE).write_text(
        _page("<h1>Review the target model</h1>\n"), encoding="utf-8"
    )
    assert ui_words_check.main() == 1
    assert f"{GOVUK_ROOT}/{PLANTED_TEMPLATE}:" in capsys.readouterr().out


def test_a_colour_outside_the_tokens_in_the_govuk_tree_is_flagged_by_the_colour_check(
    govuk_core: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import colour_drift_check

    scanned = tuple(
        (_moved(root, govuk_core), exempt) for root, exempt in colour_drift_check.SCANNED
    )
    monkeypatch.setattr(colour_drift_check, "SCANNED", scanned)
    monkeypatch.setattr(colour_drift_check, "CORE", govuk_core)
    pages_roots = tuple(_moved(p, govuk_core) for p in colour_drift_check.PAGES_ROOTS)
    monkeypatch.setattr(colour_drift_check, "PAGES_ROOTS", pages_roots)
    assert colour_drift_check.main() == 0, "the real tree-govuk is not clean"
    capsys.readouterr()
    (govuk_core / GOVUK_ROOT / PLANTED_TEMPLATE).write_text(
        _page('<svg><path fill="#ff00aa" d="M0 0"/></svg>\n'), encoding="utf-8"
    )
    assert colour_drift_check.main() == 1
    out = capsys.readouterr()
    assert f"{GOVUK_ROOT}/{PLANTED_TEMPLATE}:" in out.out + out.err


def test_a_branch_word_in_the_govuk_tree_is_flagged_by_the_no_branches_check(
    govuk_core: Path,
) -> None:
    scanned = no_branches_check.SCANNED
    assert no_branches_check.findings(no_branches_check.tree_files(govuk_core, scanned)) == []
    (govuk_core / GOVUK_ROOT / PLANTED_TEMPLATE).write_text(
        _page('<a href="/v1/investigations/{{ id }}/branch-by-filter">Branch</a>\n'),
        encoding="utf-8",
    )
    found = no_branches_check.findings(no_branches_check.tree_files(govuk_core, scanned))
    assert [f[0] for f in found] == [f"{GOVUK_ROOT}/{PLANTED_TEMPLATE}"], found


def test_an_inline_style_in_the_govuk_tree_is_flagged_by_the_design_detector(
    govuk_core: Path,
) -> None:
    roots = [_moved(Path(p), govuk_core) for p in design_check.SCANNED]
    roots = [r for r in roots if r.exists()]
    clean = design_check.unexcused(design_check.detect(roots))
    assert clean == [], "the real tree-govuk is not clean"
    stripe = (
        '<div class="card" style="border-left: 4px solid red; border-radius: 8px; '
        'padding: 8px 12px; background: var(--surface-raised)">A status</div>\n'
    )
    (govuk_core / GOVUK_ROOT / PLANTED_TEMPLATE).write_text(_page(stripe), encoding="utf-8")
    found = design_check.unexcused(design_check.detect(roots))
    assert [(Path(f["file"]).name, f["antipattern"]) for f in found] == [
        (PLANTED_TEMPLATE, "side-tab")
    ], found
