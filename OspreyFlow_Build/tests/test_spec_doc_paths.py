"""`tools/spec_doc_paths.py`: the link and build-calendar gates scan every spec document, sub-folders
included (the owner's ruling of 7 November 2026). Rule 15: the violation is planted in a spec
sub-folder, the place the old fixed list could not see."""

from __future__ import annotations

from pathlib import Path

from tools import product_tree_link_check, provenance_annotation_check
from tools.layout import REPO
from tools.spec_doc_paths import EXCLUDED, SCANNED_DOC_PATHS, spec_doc_paths


def _tree(tmp_path: Path) -> Path:
    nested = tmp_path / "spec" / "new_redesign"
    nested.mkdir(parents=True)
    (nested / "MAP.md").write_text(
        "# A design note\n\nAs `process/CLAUDE.md` rule 3 says, and as found in Phase 4, ...\n"
    )
    (tmp_path / "spec" / "ADR_RESERVATIONS.md").write_text("| ADR-150 | Phase 9 as built | x |\n")
    return tmp_path


def test_a_spec_subfolder_document_is_scanned_by_both_gates(tmp_path: Path) -> None:
    paths = spec_doc_paths(_tree(tmp_path))
    assert [p.name for p in paths] == ["MAP.md"]
    assert [m for _f, _n, m in product_tree_link_check.find_violations(paths)] == ["process/"]
    assert "Phase 4" in [m for _f, _n, m in provenance_annotation_check.find_violations(paths)]


def test_the_real_scan_covers_every_spec_document_but_the_three_excluded() -> None:
    every = {p for p in (REPO / "spec").rglob("*.md")}
    expected = every - {REPO / e for e in EXCLUDED}
    assert expected <= set(SCANNED_DOC_PATHS)
    assert REPO / "spec" / "glass_redesign" / "ALERTS_GAP_MAP.md" in SCANNED_DOC_PATHS
    assert not {REPO / e for e in EXCLUDED} & set(SCANNED_DOC_PATHS)


def test_both_gates_default_to_the_wider_set() -> None:
    assert product_tree_link_check.find_violations.__defaults__ == (SCANNED_DOC_PATHS,)
    assert provenance_annotation_check.find_violations.__defaults__ == (SCANNED_DOC_PATHS,)
