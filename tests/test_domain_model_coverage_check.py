"""The drift gate `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry names:
`scripts/domain_model_coverage_check.py`'s own docstring has the full reasoning.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from domain_model_coverage_check import (  # noqa: E402
    DOC_PATH,
    DOMAIN_MODULE_PATH,
    find_stale_entries,
    find_undocumented,
    list_domain_classes,
    load_allowlist,
)


def test_no_new_drift_beyond_the_allowlist() -> None:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    allowlist = load_allowlist()

    undocumented = find_undocumented(doc_text, classes)
    new_drift = sorted(set(undocumented) - allowlist)

    assert new_drift == [], (
        f"{DOC_PATH.name} is missing class(es) not in the allowlist: {new_drift} — "
        "a class was added to domain.py with no matching documentation, and no allowlist entry "
        "recording it as known debt either."
    )


def test_no_stale_allowlist_entries() -> None:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    allowlist = load_allowlist()

    stale = find_stale_entries(doc_text, classes, allowlist)

    assert stale == [], (
        f"stale allowlist entr(ies): {stale} — already documented, or no longer a class in "
        "domain.py; remove them so the allowlist reflects only real, current debt."
    )


def test_the_check_fails_for_a_class_the_doc_does_not_document() -> None:
    """Proves the gate is not vacuous — `CLAUDE.md` rule 12: name the test that would fail."""
    doc_text = "This doc never mentions the fictional class at all."

    undocumented = find_undocumented(doc_text, ["TotallyFictionalModel"])

    assert undocumented == ["TotallyFictionalModel"]


def test_an_allowlist_entry_already_documented_is_reported_stale() -> None:
    doc_text = "This doc now documents AlreadyFixedModel in full."
    classes = ["AlreadyFixedModel"]
    allowlist = {"AlreadyFixedModel"}

    stale = find_stale_entries(doc_text, classes, allowlist)

    assert stale == ["AlreadyFixedModel"]
