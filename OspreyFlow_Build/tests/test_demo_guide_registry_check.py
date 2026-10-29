"""The drift gate the documentation-refresh work names:
`tools/demo_guide_check.py`'s own docstring has the full reasoning for why `DEMO_REGISTRY` is a
stand-in for ADR-035's own still-unbuilt fail-closed registry, not the real thing.
"""

from __future__ import annotations

import sys

from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools"))

from demo_guide_check import (  # noqa: E402
    DEMO_GUIDE_PATH,
    DEMO_REGISTRY,
    TABLE_ROW_ENTRIES,
    find_undocumented,
)


def test_every_registered_demo_is_documented_with_its_distribution_class() -> None:
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    missing = find_undocumented(guide_text)
    assert missing == [], (
        f"{DEMO_GUIDE_PATH.name} is missing a name or distribution-class marker for: {missing} "
        "— a demo was added or reclassified without the guide being updated to match."
    )


def test_the_check_fails_for_a_registered_demo_the_guide_does_not_document() -> None:
    """Proves the gate is not vacuous by naming the test that would fail."""
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    registry_plus_one = (*DEMO_REGISTRY, ("Totally Fictional Demo XYZ", "shipped"))

    missing = find_undocumented(guide_text, registry_plus_one)

    assert missing == ["Totally Fictional Demo XYZ"]


def test_the_check_fails_for_a_registered_demo_documented_with_no_distribution_class() -> None:
    guide_text = "This guide mentions Totally Fictional Demo XYZ but never says which class it is."
    registry = (("Totally Fictional Demo XYZ", "shipped"),)

    missing = find_undocumented(guide_text, registry)

    assert missing == ["Totally Fictional Demo XYZ"]


def test_the_prison_intelligence_dataset_is_registered_and_documented_as_shipped() -> None:
    """ADR-127 Amendment 23, "The registration": a `DEMO_GUIDE.md` row, and the gate covers it."""
    assert ("Prison Intelligence Dataset", "shipped") in DEMO_REGISTRY
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    assert "Prison Intelligence Dataset" in guide_text


def test_the_check_fails_when_the_prison_intelligence_row_is_taken_out_of_the_guide() -> None:
    """The guide as it stands, with every line that names the dataset removed: the gate names it
    (the real guide, the real registry, so what fails is the entry itself)."""
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    without = "\n".join(
        line for line in guide_text.splitlines() if "Prison Intelligence Dataset" not in line
    )
    # The scale cohort's row names it too (ADR-127 Amendment 40), so both go.
    assert find_undocumented(without) == [
        "Prison Intelligence Dataset",
        "Prison Intelligence Dataset: scale cohort",
    ]


# --- ADR-127 Amendment 30: the dataset's own table row, not its name anywhere --------------------


def test_the_prison_intelligence_dataset_must_have_a_row_of_its_own_in_the_table() -> None:
    assert "Prison Intelligence Dataset" in TABLE_ROW_ENTRIES
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    rows = [
        line
        for line in guide_text.splitlines()
        if line.lstrip().startswith("|") and "**Prison Intelligence Dataset (synthetic)**" in line
    ]
    assert len(rows) == 1 and "`shipped`" in rows[0]


def test_the_check_fails_when_the_name_and_the_class_are_in_the_guide_but_not_in_a_row() -> None:
    """The real guide with the dataset's table row taken out and its name left in the prose around
    it: the old check (the name and the class marker anywhere in the text) passed this; the gate
    names the dataset now."""
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    without_row = "\n".join(
        line
        for line in guide_text.splitlines()
        if not (
            line.lstrip().startswith("|") and "**Prison Intelligence Dataset (synthetic)**" in line
        )
    )
    assert "Prison Intelligence Dataset" in without_row, "the name is still in the prose"
    assert "`shipped`" in without_row, "and the class marker is elsewhere in the guide"
    assert find_undocumented(without_row) == ["Prison Intelligence Dataset"]


def test_a_row_that_names_the_dataset_but_not_its_class_is_not_a_documented_row() -> None:
    guide_text = (
        "The Prison Intelligence Dataset is described below. `shipped` is a word used elsewhere.\n"
        "| **Prison Intelligence Dataset (synthetic)** | built | nothing about its class |\n"
    )
    registry = (("Prison Intelligence Dataset", "shipped"),)
    assert find_undocumented(guide_text, registry) == ["Prison Intelligence Dataset"]
    row = "| **Prison Intelligence Dataset (synthetic)** | `shipped` | built |\n"
    assert find_undocumented(row, registry) == []


def test_an_entry_not_named_as_a_table_row_is_still_judged_by_the_looser_rule() -> None:
    """Only the entries in `TABLE_ROW_ENTRIES` are held to a row; the rest keep their old check."""
    guide_text = "Operation Ledger is a `shipped` demo, said in a sentence and not in a table."
    assert find_undocumented(guide_text, (("Operation Ledger", "shipped"),)) == []


# --- ADR-127 Amendment 40: the scale cohort's row names the main dataset too ------------------


def test_the_scale_cohort_has_a_row_of_its_own_in_the_table() -> None:
    assert ("Prison Intelligence Dataset: scale cohort", "shipped") in DEMO_REGISTRY
    assert "Prison Intelligence Dataset: scale cohort" in TABLE_ROW_ENTRIES
    assert find_undocumented(DEMO_GUIDE_PATH.read_text(encoding="utf-8")) == []


def test_the_main_row_taken_out_is_caught_though_the_scale_row_names_the_dataset_too() -> None:
    """With only the main pack's row removed, the scale cohort's row still contains the words
    "Prison Intelligence Dataset" and the class marker. A name matched as a substring would pass
    it; the gate must name the main entry missing."""
    guide_text = DEMO_GUIDE_PATH.read_text(encoding="utf-8")
    without_main = "\n".join(
        line
        for line in guide_text.splitlines()
        if not (
            line.lstrip().startswith("|") and "**Prison Intelligence Dataset (synthetic)**" in line
        )
    )
    assert "| **Prison Intelligence Dataset: scale cohort" in without_main
    assert find_undocumented(without_main) == ["Prison Intelligence Dataset"]

