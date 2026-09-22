"""The drift gate `07_BUILD_PLAN.md`'s Phase 8 documentation-refresh entry names:
`scripts/domain_model_coverage_check.py`'s own docstring has the full triage and rule reasoning.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from domain_model_coverage_check import (  # noqa: E402
    DOMAIN_MODULE_PATH,
    _read_all_docs,
    find_stale_entries,
    find_undocumented,
    is_not_scoped,
    list_domain_classes,
    load_allowlist,
)


def test_no_new_drift_beyond_the_allowlist() -> None:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    all_docs_text = _read_all_docs()
    allowlist = load_allowlist()

    undocumented = find_undocumented(all_docs_text, classes)
    new_drift = sorted(set(undocumented) - allowlist)

    assert new_drift == [], (
        f"class(es) not documented in any Apache-scoped doc and not in the allowlist: "
        f"{new_drift} — a class was added to domain.py with no matching documentation, and no "
        "allowlist entry recording it as known debt either."
    )


def test_no_stale_allowlist_entries() -> None:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    all_docs_text = _read_all_docs()
    allowlist = load_allowlist()

    stale = find_stale_entries(all_docs_text, classes, allowlist)

    assert stale == [], (
        f"stale allowlist entr(ies): {stale} — already documented, now NOT_SCOPED, or no longer "
        "a class in domain.py; remove them so the allowlist reflects only real, current debt."
    )


def test_the_check_fails_for_a_class_the_doc_does_not_document() -> None:
    """Proves the gate is not vacuous — `CLAUDE.md` rule 12: name the test that would fail."""
    undocumented = find_undocumented(
        "This doc never mentions the fictional class at all.",
        [("TotallyFictionalModel", ["BaseModel"])],
    )

    assert undocumented == ["TotallyFictionalModel"]


def test_a_class_documented_in_a_different_apache_doc_does_not_count_as_drift() -> None:
    """The ELSEWHERE fix: `find_undocumented` is handed every Apache-scoped doc's text
    concatenated, not only `01_DOMAIN_MODEL.md`'s — a class named in `00_ARCHITECTURE.md` (as
    `OntologySchema`/`SchemaReport` genuinely are, in the `GraphPort` protocol listing) must not
    be flagged."""
    all_docs_text = "01_DOMAIN_MODEL.md has nothing here.\n00_ARCHITECTURE.md: SchemaReport"

    undocumented = find_undocumented(all_docs_text, [("SchemaReport", ["BaseModel"])])

    assert undocumented == []


def test_a_str_enum_is_not_scoped() -> None:
    assert is_not_scoped("PoleClass", ["StrEnum"]) is True


def test_a_write_counterpart_is_not_scoped() -> None:
    assert is_not_scoped("NodeWrite", ["BaseModel"]) is True


def test_an_ordinary_base_model_is_in_scope() -> None:
    assert is_not_scoped("Hotlist", ["BaseModel"]) is False


def test_an_allowlist_entry_already_documented_is_reported_stale() -> None:
    all_docs_text = "This doc now documents AlreadyFixedModel in full."
    classes = [("AlreadyFixedModel", ["BaseModel"])]
    allowlist = {"AlreadyFixedModel"}

    stale = find_stale_entries(all_docs_text, classes, allowlist)

    assert stale == ["AlreadyFixedModel"]


def test_an_allowlist_entry_that_became_not_scoped_is_reported_stale() -> None:
    """A class reclassified to a `StrEnum` (or given a `<X>Write` docstring) after being
    allowlisted must be removed by hand, not left exempting nothing under the old reasoning."""
    all_docs_text = "irrelevant"
    classes = [("ReclassifiedModel", ["StrEnum"])]
    allowlist = {"ReclassifiedModel"}

    stale = find_stale_entries(all_docs_text, classes, allowlist)

    assert stale == ["ReclassifiedModel"]
