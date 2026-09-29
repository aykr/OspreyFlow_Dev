"""The drift gate the documentation-refresh work names:
`tools/domain_model_coverage_check.py`'s own docstring has the full triage and rule reasoning,
including why the search is single-document (`01_DOMAIN_MODEL.md`), not every Apache-scoped doc.
"""

from __future__ import annotations

import sys

from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools"))

from domain_model_coverage_check import (  # noqa: E402
    DOC_PATH,
    DOMAIN_MODULE_PATH,
    find_stale_entries,
    find_undocumented,
    is_not_scoped,
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
        f"class(es) not documented in {DOC_PATH.name} and not in the allowlist: {new_drift} — a "
        "class was added to domain.py with no matching documentation, and no allowlist entry "
        "recording it as known debt either."
    )


def test_no_stale_allowlist_entries() -> None:
    classes = list_domain_classes(DOMAIN_MODULE_PATH.read_text(encoding="utf-8"))
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    allowlist = load_allowlist()

    stale = find_stale_entries(doc_text, classes, allowlist)

    assert stale == [], (
        f"stale allowlist entr(ies): {stale} — already documented, now NOT_SCOPED, or no longer "
        "a class in domain.py; remove them so the allowlist reflects only real, current debt."
    )


def test_the_check_fails_for_a_class_the_doc_does_not_document() -> None:
    """Proves the gate is not vacuous by naming the test that would fail."""
    undocumented = find_undocumented(
        "This doc never mentions the fictional class at all.",
        [("TotallyFictionalModel", ["BaseModel"])],
    )

    assert undocumented == ["TotallyFictionalModel"]


def test_a_bare_name_mention_in_a_protocol_signature_still_counts_as_undocumented() -> None:
    """The ELSEWHERE bar, applied: a class name appearing only inside a signature (a type
    reference, not a definition of the class's own fields/identity/lifecycle/access) must still be
    flagged. A first version of this gate treated *any* mention anywhere as documentation and
    wrongly cleared `OntologySchema`/`SchemaReport` on exactly this shape of text — this test pins
    the regression directly, at the single-document search the mechanism was narrowed back to."""
    doc_text = "async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ..."

    undocumented = find_undocumented(doc_text, [("OntologySchema", ["BaseModel"])])

    assert undocumented == ["OntologySchema"]


def test_a_str_enum_is_not_scoped() -> None:
    assert is_not_scoped("PoleClass", ["StrEnum"]) is True


def test_a_write_counterpart_is_not_scoped() -> None:
    assert is_not_scoped("NodeWrite", ["BaseModel"]) is True


def test_an_ordinary_base_model_is_in_scope() -> None:
    assert is_not_scoped("Hotlist", ["BaseModel"]) is False


def test_an_allowlist_entry_already_documented_is_reported_stale() -> None:
    doc_text = "This doc now documents AlreadyFixedModel in full."
    classes = [("AlreadyFixedModel", ["BaseModel"])]
    allowlist = {"AlreadyFixedModel"}

    stale = find_stale_entries(doc_text, classes, allowlist)

    assert stale == ["AlreadyFixedModel"]


def test_an_allowlist_entry_that_became_not_scoped_is_reported_stale() -> None:
    """A class reclassified to a `StrEnum` (or given a `<X>Write` docstring) after being
    allowlisted must be removed by hand, not left exempting nothing under the old reasoning."""
    doc_text = "irrelevant"
    classes = [("ReclassifiedModel", ["StrEnum"])]
    allowlist = {"ReclassifiedModel"}

    stale = find_stale_entries(doc_text, classes, allowlist)

    assert stale == ["ReclassifiedModel"]
