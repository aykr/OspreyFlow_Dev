"""The link-integrity gate this repository's own decision log names — `scripts/product_tree_link_
check.py`'s own docstring has the full reasoning, including why it is scoped to documentation-to-
documentation references only, not every citation in the repository."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages"))

from scripts.product_tree_link_check import (  # noqa: E402
    ALLOWLIST_PATH,
    _load_allowlist,
    find_violations,
)
from scripts.route_coverage_check import APACHE_DOC_PATHS  # noqa: E402


def test_no_new_private_tree_references_beyond_the_allowlist() -> None:
    violations = find_violations()
    allowlisted = _load_allowlist()
    new_violations = [
        (path, lineno, marker)
        for path, lineno, marker in violations
        if (path, marker) not in allowlisted
    ]
    assert new_violations == [], (
        f"new private-tree reference(s) from an Apache-scoped document: {new_violations}. "
        f"Either fix the reference, or add it to "
        f"{ALLOWLIST_PATH.relative_to(REPO_ROOT)} if genuinely already known."
    )


def test_the_checker_actually_flags_a_private_tree_citation(tmp_path: Path) -> None:
    """Non-vacuous, the same discipline this repository's own other two drift gates
    (`route_coverage_check.py`, `domain_model_coverage_check.py`) are already held to: a
    deliberately planted violation, proving the pattern can fail, not only that it currently
    passes. Real, isolated fixture files — not this repository's own real docs — so this test's
    own result never depends on what the live allowlist happens to contain."""
    clean_doc = tmp_path / "clean.md"
    clean_doc.write_text(
        "# A clean document\n\nNo private-tree reference anywhere in this file.\n",
        encoding="utf-8",
    )
    dirty_doc = tmp_path / "dirty.md"
    dirty_doc.write_text(
        "# A document with a real violation\n\nSee `06_DECISIONS.md` ADR-034 for the full "
        "reasoning.\n",
        encoding="utf-8",
    )

    clean_violations = find_violations((clean_doc,))
    assert clean_violations == []

    dirty_violations = find_violations((dirty_doc,))
    assert len(dirty_violations) == 1
    (path, lineno, marker) = dirty_violations[0]
    assert path == str(dirty_doc)
    assert lineno == 3
    assert marker == "06_DECISIONS.md"


def test_apache_doc_paths_is_the_same_set_route_coverage_check_uses() -> None:
    """The two gates share one definition of "product tree" (`scripts/product_tree_link_check.py`'s
    own docstring: imported, not redeclared) — this pins that they cannot silently diverge."""
    from scripts.product_tree_link_check import find_violations as _find

    assert _find.__defaults__[0] is APACHE_DOC_PATHS
