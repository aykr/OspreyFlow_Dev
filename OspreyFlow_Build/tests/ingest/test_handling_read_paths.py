"""ADR-127 decision 3, rule 4: the paths that show a source's values before or outside resolution.

A recipe that binds a marking to a column makes the source's own marking only the lowest a row may
carry. A path that masked by it alone would show a SECRET row to a reader cleared for the source's
OFFICIAL. What a mistake would do, and the case that catches it:

- Verify showing a SECRET row's simulated node, link or rejected row to an OFFICIAL author
  (`test_verify_masks_each_node_by_its_own_marking`, `..._a_rejected_row_by_every_marking`);
- Profile showing the raw cells (`test_profile_masks_for_a_reader_who_may_not_view_every_marking`);
- the Map sample row showing a SECRET row's cells (`test_the_sample_row_...`);
- the same paths masking a source that binds nothing, which the source's marking alone still
  decides (the `..._binds_nothing` cases);
- Verify not judging a bound marking at all (`test_verify_judges_a_bound_marking`).

The draft is in memory and the source's rows are supplied where each module reads them."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api import studio_map, studio_profile, studio_verify
from services.api.studio_map import get_sample_row
from services.api.studio_profile import profile_recipe_source
from services.api.studio_verify import run_verify

from schemas.domain import Principal
from schemas.ingest import RowTemplate, StudioRecipeDraft, StudioRecipeStatus
from tests.ingest.recipe_test_support import ValidatingGraph
from tests.ingest.test_handling_from_columns import ONTOLOGY, SCHEME, UNITS, _bound

BASE = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
    "units": UNITS,
}
OFFICIAL = Principal(id="author-o", clearance="OFFICIAL", org_unit="unit-1")
CLEARED = Principal(id="author-s", clearance="SECRET", org_unit="unit-1")
ROWS = [
    {"title": "Open report", "classification": ""},
    {"title": "Hidden report", "classification": "SECRET"},
    {"title": "Odd report", "classification": "TOP-SECRET"},
]


def _draft(*, binds: bool) -> StudioRecipeDraft:
    entity: dict[str, Any] = {
        "ref": "doc",
        "pole_class": "object",
        "type": "Document",
        "properties": {"title": {"field": "title"}},
    }
    if binds:
        entity["handling"] = _bound("classification")
    return StudioRecipeDraft(
        recipe_id="r-1",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="Reports",
        connector_profile="generic-csv",
        source_location="reports.csv",
        handling=dict(BASE),
        legal_basis="Test",
        owning_unit="unit-1",
        created_by="author-o",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        row_template=RowTemplate.model_validate({"entities": [entity], "edges": []}),
        ready_for_profile=True,
    )


@pytest.fixture(autouse=True)
def _rows(monkeypatch: pytest.MonkeyPatch) -> None:
    for module, name in (
        (studio_verify, "_read_recipe_rows"),
        (studio_map, "_read_recipe_rows"),
        (studio_profile, "_read_rows"),
    ):
        monkeypatch.setattr(module, name, lambda draft: [dict(r) for r in ROWS])


async def _verify(principal: Principal, *, binds: bool = True) -> Any:
    return await run_verify(
        _draft(binds=binds),
        principal,
        SCHEME,
        ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ONTOLOGY,
    )


async def test_verify_masks_each_node_by_its_own_marking() -> None:
    official = await _verify(OFFICIAL)
    titles = {str(n.properties["title"]): n.handling.classification for n in official.nodes}
    assert "Open report" in titles  # an OFFICIAL row is shown to an OFFICIAL author
    assert "Hidden report" not in titles  # a SECRET row's value is not
    secret_nodes = [n for n in official.nodes if n.handling.classification == "SECRET"]
    assert len(secret_nodes) == 1 and secret_nodes[0].properties["title"] != "Hidden report"
    assert official.values_masked is True
    cleared = await _verify(CLEARED)
    assert {str(n.properties["title"]) for n in cleared.nodes} == {"Open report", "Hidden report"}
    assert cleared.values_masked is False


async def test_verify_masks_a_rejected_row_by_every_marking() -> None:
    official = await _verify(OFFICIAL)
    (group,) = official.rejections
    assert "TOP-SECRET" not in group.reason and "does not define" in group.reason
    assert all("TOP-SECRET" not in s.sample and "Odd report" not in s.sample for s in group.samples)
    cleared = await _verify(CLEARED)
    (group,) = cleared.rejections
    assert any("Odd report" in s.sample for s in group.samples)


async def test_verify_of_a_source_that_binds_nothing_is_judged_by_the_sources_marking() -> None:
    report = await _verify(OFFICIAL, binds=False)
    assert report.values_masked is False
    assert "Hidden report" in {str(n.properties["title"]) for n in report.nodes}


async def test_verify_judges_a_bound_marking() -> None:
    report = await _verify(CLEARED)
    assert report.rows_read == 3
    (group,) = report.rejections
    assert "TOP-SECRET" not in group.reason and "does not define" in group.reason
    assert {n.handling.classification for n in report.nodes} == {"OFFICIAL", "SECRET"}


async def test_profile_masks_for_a_reader_who_may_not_view_every_marking() -> None:
    official = await profile_recipe_source(_draft(binds=True), OFFICIAL, SCHEME)
    assert official.values_masked is True
    cleared = await profile_recipe_source(_draft(binds=True), CLEARED, SCHEME)
    assert cleared.values_masked is False


async def test_profile_of_a_source_that_binds_nothing_binds_nothing() -> None:
    assert (
        await profile_recipe_source(_draft(binds=False), OFFICIAL, SCHEME)
    ).values_masked is False


async def test_the_sample_row_masks_for_a_reader_who_may_not_view_every_marking() -> None:
    official = await get_sample_row(_draft(binds=True), OFFICIAL, SCHEME, 1)
    assert official.values_masked is True and official.values["title"] != "Hidden report"
    cleared = await get_sample_row(_draft(binds=True), CLEARED, SCHEME, 1)
    assert cleared.values_masked is False and cleared.values["title"] == "Hidden report"


async def test_the_sample_row_of_a_source_that_binds_nothing_binds_nothing() -> None:
    row = await get_sample_row(_draft(binds=False), OFFICIAL, SCHEME, 1)
    assert row.values_masked is False and row.values["title"] == "Hidden report"


# --- Profile and the sample row before a template exists (Connect declares the column) ---


def _declared_draft() -> StudioRecipeDraft:
    draft = _draft(binds=False)
    return draft.model_copy(
        update={
            "row_template": None,
            "handling": {
                **draft.handling,
                "handling_columns": {"classification": "classification"},
            },
        }
    )


async def test_the_first_profile_before_map_is_masked_by_the_declared_column() -> None:
    official = await profile_recipe_source(_declared_draft(), OFFICIAL, SCHEME)
    assert official.values_masked is True
    cleared = await profile_recipe_source(_declared_draft(), CLEARED, SCHEME)
    assert cleared.values_masked is False


async def test_the_sample_row_before_map_is_masked_row_by_row() -> None:
    rows = [await get_sample_row(_declared_draft(), OFFICIAL, SCHEME, i) for i in range(len(ROWS))]
    # Row 2 (index 1) says SECRET, row 3 (index 2) names a grade the scheme lacks: both masked.
    assert [r.values_masked for r in rows] == [False, True, True]
    assert rows[0].values["title"] == "Open report"
    cleared = await get_sample_row(_declared_draft(), CLEARED, SCHEME, 1)
    assert cleared.values_masked is False and cleared.values["title"] == "Hidden report"


async def test_a_declared_column_the_source_lacks_is_treated_as_the_strictest() -> None:
    draft = _declared_draft().model_copy(
        update={
            "handling": {**BASE, "handling_columns": {"classification": "grade"}},
        }
    )
    row = await get_sample_row(draft, OFFICIAL, SCHEME, 0)
    assert row.values_masked is True


# --- review round 4: fail closed on an empty candidate list; combinations over each element's base


def _use_rows(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, str]]) -> None:
    for module, name in (
        (studio_verify, "_read_recipe_rows"),
        (studio_map, "_read_recipe_rows"),
        (studio_profile, "_read_rows"),
    ):
        monkeypatch.setattr(module, name, lambda draft: [dict(r) for r in rows])


def _no_units_draft() -> StudioRecipeDraft:
    """A source that declares a classification column and a unit column but no `units`, built
    directly: Connect refuses this declaration, so the read paths must not rely on that."""
    draft = _draft(binds=False)
    handling = {k: v for k, v in draft.handling.items() if k != "units"}
    handling["handling_columns"] = {"classification": "cls", "owning_unit": "unit"}
    return draft.model_copy(update={"row_template": None, "handling": handling})


UNIT_ROWS = [
    {"title": "Open report", "cls": "", "unit": ""},
    {"title": "Hidden report", "cls": "SECRET", "unit": "unit-9"},  # no units to name it by
]


def test_row_markings_with_no_units_to_name_say_the_row_is_unviewable() -> None:
    from services.api.studio_profile import row_markings

    result = row_markings(_no_units_draft(), SCHEME, UNIT_ROWS[1])
    assert result.unviewable is True
    assert row_markings(_no_units_draft(), SCHEME, UNIT_ROWS[0]).unviewable is False


def _scheme_without_a_restricted_code() -> Any:
    from ontology.handling import HandlingCode, HandlingScheme

    return HandlingScheme.model_validate(
        {
            **SCHEME.model_dump(),
            "handling_codes": {
                "P": HandlingCode.model_validate(
                    {"label": "Permitted", "dissemination": "permitted"}
                )
            },
        }
    )


async def test_an_unviewable_row_is_masked_for_a_principal_cleared_for_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no restricted code in the scheme, and a principal whose unit is called anything at all,
    "unviewable" must not depend on a stand-in marking: it is a fact about the row."""
    _use_rows(monkeypatch, UNIT_ROWS)
    scheme = _scheme_without_a_restricted_code()
    draft = _no_units_draft()
    top = Principal(id="top", clearance="SECRET", org_unit="unit-1")
    assert (await get_sample_row(draft, top, scheme, 1)).values_masked is True
    assert (await profile_recipe_source(draft, top, scheme)).values_masked is True
    odd_unit = Principal(id="odd", clearance="SECRET", org_unit="(no unit)")
    assert (await get_sample_row(draft, odd_unit, SCHEME, 1)).values_masked is True
    assert (await profile_recipe_source(draft, odd_unit, SCHEME)).values_masked is True
    # A row that can be resolved is still shown to a reader cleared for it.
    assert (await get_sample_row(draft, top, scheme, 0)).values_masked is False


async def test_profile_sample_and_verify_mask_when_a_unit_part_has_no_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_rows(monkeypatch, UNIT_ROWS)
    draft = _no_units_draft()
    assert (await profile_recipe_source(draft, OFFICIAL, SCHEME)).values_masked is True
    assert (await get_sample_row(draft, OFFICIAL, SCHEME, 1)).values_masked is True
    # A row that is rejected resolves to no marking: Verify masks it by this row's possible ones.
    rows = [{"title": "", "cls": "SECRET", "unit": "unit-9"}]
    _use_rows(monkeypatch, rows)
    with_template = draft.model_copy(update={"row_template": _draft(binds=False).row_template})
    report = await run_verify(
        with_template,
        OFFICIAL,
        SCHEME,
        ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ONTOLOGY,
    )
    (group,) = report.rejections
    assert all("SECRET" not in sample.sample for sample in group.samples)
    assert report.values_masked is True


async def test_a_row_is_masked_by_the_element_that_reads_it_not_the_source_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The element fixes both units to unit-2 and binds the handling code: a cell `R` makes the
    row restricted for unit-2. A unit-1 reader who may receive `R` may view the source's own unit-1
    marking, which is not what the row carries."""
    _use_rows(monkeypatch, [{"title": "Elsewhere", "handling_code": "R"}])
    element: dict[str, Any] = {
        "ref": "doc",
        "pole_class": "object",
        "type": "Document",
        "properties": {"title": {"field": "title"}},
        "handling": {
            "originator": "unit-2",
            "owning_unit": "unit-2",
            **_bound("handling_code"),
        },
    }
    draft = _draft(binds=False).model_copy(
        update={"row_template": RowTemplate.model_validate({"entities": [element], "edges": []})}
    )
    unit1_receiver = Principal(
        id="reader-u1",
        clearance="OFFICIAL",
        org_unit="unit-1",
        receivable_handling_codes=["R"],
    )
    row = await get_sample_row(draft, unit1_receiver, SCHEME, 0)
    assert row.values_masked is True
    unit2_receiver = unit1_receiver.model_copy(update={"org_unit": "unit-2"})
    assert (await get_sample_row(draft, unit2_receiver, SCHEME, 0)).values_masked is False
