"""ADR-127 decision 3, the cases a review of `test_handling_from_columns.py` found missing. What a
mistake would do, and the case that catches it:

- a duplicate group marked by its survivor alone, so a SECRET duplicate of an OFFICIAL row is
  stored OFFICIAL (`test_a_secret_duplicate_marks_its_survivor_secret`, and the group refusals);
- a link's bound marking lost between resolution and write, the staged round trip
  (`test_a_links_bound_marking_survives_staging`);
- held content marked by the recipe, not by the row that holds it
  (`test_held_content_takes_its_holders_row_marking`);
- a map point under the first row's marking
  (`test_a_point_takes_the_rows_marking_and_a_shared_point_the_strictest`);
- a held row stored under the recipe's first unit (`test_a_held_row_is_marked_by_its_own_row`);
- the markings an alert is built from missing what a column can bind
  (`test_recipe_handlings_gives_every_marking_a_binding_can_take`);
- a run with no scheme loading rows nothing could judge (`test_a_run_with_no_scheme_refuses...`);
- the source's own marking not binding an element's fixed values in every part, at save and at run
  (`test_a_fixed_handling_looser_than_the_sources_is_refused...`);
- a provenance column, or a misspelt handling key, silently ignored
  (`test_a_provenance_column_and_an_unknown_handling_key_are_refused`);
- the draft's units lost between Connect, Map, publish and the run
  (`test_units_survive_connect_patch_map_and_publish`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from services.api.rule_evaluation import held_rows_for
from services.api.studio_map import HandlingLoosenedError, draft_units, validate_handling_tightens
from services.api.studio_publish import build_recipe, serialise_recipe
from services.ingest.engine import dry_run_recipe, recipe_handlings, row_marking
from services.ingest.geometries import point_geometries
from services.ingest.recipe_rules import RecipeRuleError, recipe_rule_violations

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.domain import Handling, Principal
from schemas.ingest import (
    ConnectDraftInput,
    Recipe,
    RecipeDefaults,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    ValidatingGraph,
    local_staging,
)
from tests.ingest.test_handling_from_columns import (
    FIELDS,
    LOADER,
    ONTOLOGY,
    SCHEME,
    UNITS,
    _bound,
    _row,
)
from tests.ingest.test_handling_from_columns import _run as _run_recipe

BASE = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def _make(
    entities: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    *,
    defaults: dict[str, Any] | None = None,
    units: list[str] | None = UNITS,
    deduplicate: list[dict[str, Any]] | None = None,
    connector: dict[str, Any] | None = None,
) -> Recipe:
    body: dict[str, Any] = {
        "id": "review",
        "version": 1,
        "label": "Review",
        "connector": connector or {"profile": "csv"},
        "ontology_version": ONTOLOGY.version,
        "pack_versions": {},
        "defaults": {
            "provenance": {"state": "asserted"},
            "handling": {**BASE, **(defaults or {})},
            **({"units": units} if units is not None else {}),
        },
        "row_template": {"entities": entities, "edges": edges or []},
    }
    if deduplicate is not None:
        body["deduplicate"] = {"key": deduplicate}
    return Recipe.model_validate(body)


def _document(**extra: Any) -> dict[str, Any]:
    return {
        "ref": "doc",
        "pole_class": "object",
        "type": "Document",
        "properties": {"title": {"field": "title"}},
        **extra,
    }


def _person(ref: str = "p", **extra: Any) -> dict[str, Any]:
    return {
        "ref": ref,
        "pole_class": "person",
        "type": "Person",
        "properties": {"family_name": {"field": "title"}},
        **extra,
    }


def _titles(graph: ValidatingGraph, entity_type: str = "Document") -> dict[str, Any]:
    key = "title" if entity_type == "Document" else "family_name"
    return {str(n.properties[key]): n for n in graph.committed_nodes if n.type == entity_type}


# --- duplicate groups --------------------------------------------------------------------


def _by_title() -> list[dict[str, Any]]:
    return [{"field": "title"}]


async def test_a_secret_duplicate_marks_its_survivor_secret() -> None:
    rows = [_row("same"), _row("same", classification="SECRET")]
    recipe = _make([_document(handling=_bound("classification"))], deduplicate=_by_title())
    report, graph = await _run_recipe(recipe, rows)
    assert report.rejections == [] and report.rows_deduplicated == 1
    assert _titles(graph)["same"].handling.classification == "SECRET"


async def test_a_duplicate_that_fails_rejects_the_whole_group() -> None:
    rows = [_row("same"), _row("same", classification="TOP-SECRET"), _row("other")]
    recipe = _make([_document(handling=_bound("classification"))], deduplicate=_by_title())
    report, graph = await _run_recipe(recipe, rows)
    (rejection,) = report.rejections
    assert "TOP-SECRET" not in rejection.reason and "does not define" in rejection.reason
    assert sorted(_titles(graph)) == ["other"]


async def test_duplicates_naming_different_units_under_a_restricted_code_are_rejected() -> None:
    rows = [
        _row("same", handling_code="R", owning_unit="unit-1"),
        _row("same", handling_code="R", owning_unit="unit-2"),
    ]
    recipe = _make(
        [_document(handling=_bound("handling_code", "owning_unit"))], deduplicate=_by_title()
    )
    report, graph = await _run_recipe(recipe, rows)
    (rejection,) = report.rejections
    assert "different units" in rejection.reason and "'R'" not in rejection.reason
    assert _titles(graph) == {}


# --- a link's bound marking --------------------------------------------------------------


async def test_a_links_bound_marking_survives_staging() -> None:
    entities = [_person("a"), _document()]
    edges = [
        {
            "type": "MENTIONED_IN",
            "from": "a",
            "to": "doc",
            "handling": _bound("classification", "sanitisation_code"),
        }
    ]
    rows = [_row("one", classification="SECRET", sanitisation_code="S2"), _row("two")]
    report, graph = await _run_recipe(_make(entities, edges), rows)
    assert report.rejections == [], report.rejections
    marks = sorted(
        (e.handling.classification, e.handling.sanitisation_code) for e in graph.committed_edges
    )
    assert marks == [("OFFICIAL", None), ("SECRET", "S2")]


# --- held content ------------------------------------------------------------------------


async def test_held_content_takes_its_holders_row_marking() -> None:
    holder = _person(
        handling=_bound("classification"), content={"kind": "document_text", "field": "report_text"}
    )
    rows = [_row("one", classification="SECRET"), _row("two")]
    graph = ValidatingGraph(ONTOLOGY)
    from services.api.studio_publish import load_with_rules

    report, _events, _held = await load_with_rules(
        _make([holder]),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="l",
        investigation_scope="case-1",
        source="held.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    assert report.rejections == []
    content = [n for n in graph.committed_nodes if n.id.startswith("content:")]
    assert sorted(n.handling.classification for n in content) == ["OFFICIAL", "SECRET"]
    holds = [e for e in graph.committed_edges if e.type == "HOLDS"]
    assert sorted(e.handling.classification for e in holds) == ["OFFICIAL", "SECRET"]


# --- geometry ----------------------------------------------------------------------------


def _site(*, crs: str | None = "EPSG:4326") -> Recipe:
    return _make(
        [
            {
                "ref": "site",
                "pole_class": "location",
                "type": "Location",
                "match_on": "site_ref",
                "on_match": "reference",
                "handling": _bound("classification"),
                "properties": {
                    "site_ref": {"field": "cell_id"},
                    "geometry_ref": {
                        "fields": ["longitude", "latitude"],
                        "transform": "geometry_ref",
                    },
                },
            }
        ],
        connector={"profile": "cell-site-csv", "source_crs": crs},
    )


def _mast(cell: str, lon: str, lat: str, classification: str) -> dict[str, str]:
    return {
        "cell_id": cell,
        "longitude": lon,
        "latitude": lat,
        "classification": classification,
    }


def test_a_point_takes_the_rows_marking_and_a_shared_point_the_strictest() -> None:
    rows = [
        _mast("A", "-2.2309", "53.4776", "SECRET"),
        _mast("B", "-2.2507", "53.4794", ""),
        _mast("C", "-2.2309", "53.4776", ""),  # the same place as A, from an OFFICIAL row
    ]
    points = point_geometries(_site(), rows, scheme=SCHEME)
    by_lon = {p.lon: p.handling.classification for p in points}
    assert by_lon == {-2.2309: "SECRET", -2.2507: "OFFICIAL"}
    assert len(points) == 2


def test_a_shared_point_is_secret_whichever_row_comes_first() -> None:
    rows = [
        _mast("C", "-2.2309", "53.4776", ""),
        _mast("A", "-2.2309", "53.4776", "SECRET"),
    ]
    (point,) = point_geometries(_site(), rows, scheme=SCHEME)
    assert point.handling.classification == "SECRET"


# --- held rows ---------------------------------------------------------------------------


def test_a_held_row_is_marked_by_its_own_row() -> None:
    recipe = _make([_document(handling=_bound("handling_code", "owning_unit"))])
    rows = [
        _row("plain"),
        _row("elsewhere", handling_code="R", owning_unit="unit-2"),
    ]
    marks = [row_marking(recipe, r, SCHEME) for r in rows]
    assert (marks[0].handling_code, marks[0].owning_unit) == ("P", "unit-1")
    assert (marks[1].handling_code, marks[1].owning_unit) == ("R", "unit-2")
    rule = SimpleNamespace(id="rule-1")
    verdict = SimpleNamespace(hold={0: (rule, "why"), 1: (rule, "why")})
    held = held_rows_for(
        verdict,  # type: ignore[arg-type]
        rows,
        row_numbers=None,
        investigation_id="case-1",
        recipe_id="review",
        recipe_version=1,
        load_id="l",
        source="s.csv",
        handling=Handling.model_validate(BASE),
        dataset_id=None,
        row_handling=lambda row: row_marking(recipe, row, SCHEME),
    )
    assert [(h.handling.handling_code, h.handling.owning_unit) for h in held] == [
        ("P", "unit-1"),
        ("R", "unit-2"),
    ]


async def test_a_row_whose_elements_name_different_units_under_a_restricted_code_is_rejected() -> (
    None
):
    """One `Handling` holds one unit: a row that marks its elements restricted for different units
    cannot be held or loaded as one marking, so it is rejected with its cause (ADR-127 Amendment
    2), and its neighbours load."""
    doc = _document()  # no override: carries the source's own marking, unit-1
    person = _person(handling=_bound("handling_code", "owning_unit"))
    rows = [
        _row("clash", handling_code="R", owning_unit="unit-2"),
        _row("fine", handling_code="R", owning_unit="unit-1"),
    ]
    report, graph = await _run_recipe(_make([doc, person]), rows)
    (rejection,) = report.rejections
    assert "different units under a restricted" in rejection.reason
    assert sorted(_titles(graph)) == ["fine"]


def test_row_marking_refuses_a_row_whose_elements_name_different_units() -> None:
    from services.ingest.engine import RowRejected

    recipe = _make([_document(), _person(handling=_bound("handling_code", "owning_unit"))])
    with pytest.raises(RowRejected, match="different units under a restricted"):
        row_marking(recipe, _row("clash", handling_code="R", owning_unit="unit-2"), SCHEME)


def test_row_marking_refuses_an_unresolved_row_whose_possible_markings_conflict() -> None:
    from services.ingest.engine import RowRejected

    recipe = _make([_document(handling=_bound("handling_code", "owning_unit"))])
    with pytest.raises(RowRejected, match="different units under a restricted"):
        row_marking(recipe, _row("odd", handling_code="R", owning_unit="unit-9"), SCHEME)


def test_a_held_row_whose_cell_does_not_resolve_is_held_no_lower_than_it_could_be() -> None:
    recipe = _make([_document(handling=_bound("classification"))])
    marking = row_marking(recipe, _row("odd", classification="TOP-SECRET"), SCHEME)
    assert marking.classification == "SECRET"  # the strictest the scheme defines


# --- recipe_handlings --------------------------------------------------------------------


def test_recipe_handlings_gives_every_marking_a_binding_can_take() -> None:
    recipe = _make([_document(handling=_bound("classification", "owning_unit"))])
    given = recipe_handlings(recipe, SCHEME)
    assert {h.classification for h in given} == set(SCHEME.classification)
    assert {h.owning_unit for h in given} == {"unit-1", "unit-2"}
    # Without a scheme a bound part is left at its default: no caller that judges rows has none.
    assert {h.classification for h in recipe_handlings(recipe)} == {"OFFICIAL"}


# --- no scheme ---------------------------------------------------------------------------


async def test_a_run_with_no_scheme_refuses_a_recipe_that_binds_a_marking() -> None:
    from services.api.studio_publish import load_with_rules

    recipe = _make([_document(handling=_bound("classification"))])
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="no handling scheme"):
        await load_with_rules(
            recipe,
            [_row("one")],
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="l",
            investigation_scope="case-1",
            source="s.csv",
            rules=None,
        )
    assert graph.commits == 0 and graph.committed_nodes == []


async def test_a_dry_run_with_no_scheme_refuses_a_recipe_that_binds_a_marking() -> None:
    recipe = _make([_document(handling=_bound("classification"))])
    with pytest.raises(RecipeRuleError, match="no handling scheme"):
        await dry_run_recipe(
            recipe,
            [_row("one")],
            graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=LOADER,
            source="s.csv",
        )


# --- the source's own marking binds the element's fixed values ---------------------------


def test_a_fixed_handling_looser_than_the_sources_is_refused_at_save() -> None:
    recipe = _make([_document(handling={"handling_code": "P"})], defaults={"handling_code": "R"})
    problems = recipe_rule_violations(
        recipe.row_template,
        ONTOLOGY,
        defaults_handling=recipe.defaults.handling,
        scheme=SCHEME,
    )
    assert len(problems) == 1
    assert "handling_code 'P'" in problems[0] and "'R'" in problems[0]
    tighter = _make([_document(handling={"handling_code": "R"})])
    assert (
        recipe_rule_violations(
            tighter.row_template,
            ONTOLOGY,
            defaults_handling=tighter.defaults.handling,
            scheme=SCHEME,
        )
        == []
    )


async def test_a_fixed_handling_looser_than_the_sources_is_refused_at_run() -> None:
    recipe = _make([_document(handling={"handling_code": "P"})], defaults={"handling_code": "R"})
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="handling_code 'P'"):
        await _run_recipe(recipe, [_row("one")], graph)
    assert graph.commits == 0


def test_a_fixed_handling_the_scheme_does_not_define_is_refused() -> None:
    recipe = _make([_document(handling={"action_code": "A9"})])
    (problem,) = recipe_rule_violations(
        recipe.row_template, ONTOLOGY, defaults_handling=recipe.defaults.handling, scheme=SCHEME
    )
    assert "A9" in problem and "does not define" in problem


# --- provenance and unknown keys ---------------------------------------------------------


def test_a_provenance_column_and_an_unknown_handling_key_are_refused() -> None:
    column = _make([_document(provenance={"state": {"field": "state"}})])
    (problem,) = recipe_rule_violations(column.row_template, ONTOLOGY)
    assert "provenance" in problem and "column" in problem
    typo = _make([_document(handling={"clasification": "SECRET"})])
    (problem,) = recipe_rule_violations(typo.row_template, ONTOLOGY)
    assert "clasification" in problem


# --- validate_handling_tightens ----------------------------------------------------------


def test_the_save_time_classification_check_skips_a_binding_and_judges_a_fixed_value() -> None:
    baseline = Handling.model_validate({**BASE, "classification": "SECRET"})
    validate_handling_tightens(baseline, {"classification": {"field": "classification"}}, SCHEME)
    with pytest.raises(HandlingLoosenedError):
        validate_handling_tightens(baseline, {"classification": "OFFICIAL"}, SCHEME)


# --- units: Connect, PATCH, Map, publish -------------------------------------------------


@pytest.mark.parametrize("units", ["unit-1", None, [""], ["unit-1", 3], {"a": 1}])
def test_connect_refuses_units_that_are_not_a_list_of_names(units: object) -> None:
    with pytest.raises(ValidationError, match="units"):
        ConnectDraftInput(
            label="x", connector_profile="generic-csv", handling={**BASE, "units": units}
        )


def test_connect_accepts_a_list_of_unit_names() -> None:
    body = ConnectDraftInput(
        label="x", connector_profile="generic-csv", handling={**BASE, "units": UNITS}
    )
    assert body.handling["units"] == UNITS


def test_a_patched_handling_keeps_the_drafts_units_unless_it_says_otherwise() -> None:
    old: dict[str, object] = {**BASE, "units": UNITS}
    from services.api.studio_recipes import carry_source_declarations as carry_units

    assert carry_units(old, dict(BASE)) == {**BASE, "units": UNITS}
    assert carry_units(old, {**BASE, "units": ["unit-3"]}) == {**BASE, "units": ["unit-3"]}
    assert carry_units(old, {**BASE, "units": []}) == {**BASE, "units": []}
    assert carry_units(old, None) is None
    plain: dict[str, object] = dict(BASE)
    assert carry_units(plain, dict(plain)) == plain


def _draft() -> StudioRecipeDraft:
    template = _make([_document(handling=_bound("owning_unit"))]).row_template
    return StudioRecipeDraft(
        recipe_id="r-1",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="Reports",
        connector_profile="generic-csv",
        source_location="reports.csv",
        handling={**BASE, "units": UNITS},
        legal_basis="Test",
        owning_unit="unit-1",
        created_by="loader-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        row_template=template,
        ready_for_profile=True,
    )


def test_units_survive_connect_patch_map_and_publish() -> None:
    draft = _draft()
    assert draft_units(draft) == UNITS  # what Map save reads
    defaults = RecipeDefaults.for_source(draft.handling, draft.legal_basis)
    assert defaults.units == UNITS and "units" not in defaults.handling
    built = build_recipe(
        draft,
        ontology_version=ONTOLOGY.version,
        pack_versions={},
        schedule_cron=None,
        schedule_watch=None,
    )
    assert built.defaults.units == UNITS and "units" not in built.defaults.handling
    published = Recipe.model_validate(yaml.safe_load(serialise_recipe(built)))
    assert published.defaults.units == UNITS
    # And the published recipe binds a unit it declares: the rule that reads it at save and at run.
    assert (
        recipe_rule_violations(published.row_template, ONTOLOGY, units=published.defaults.units)
        == []
    )


async def test_a_published_recipe_judges_a_bound_unit_against_its_units() -> None:
    draft = _draft()
    built = build_recipe(
        draft,
        ontology_version=ONTOLOGY.version,
        pack_versions={},
        schedule_cron=None,
        schedule_watch=None,
    )
    recipe = Recipe.model_validate(yaml.safe_load(serialise_recipe(built)))
    rows = [_row("ok", owning_unit="unit-2"), _row("stranger", owning_unit="unit-9")]
    report, graph = await _run_recipe(recipe, rows)
    assert [r.row_index for r in report.rejections] == [1]
    assert sorted(_titles(graph)) == ["ok"]


_ = (FIELDS, Principal)


# --- review round 3 ----------------------------------------------------------------------


def _fixed_units_recipe() -> Recipe:
    """Two elements with fixed handling and no column binding: restricted, for different units, on
    the rows where the gated one is present."""
    gated = _document(
        when={"field": "flag", "is": "not_null"},
        handling={"handling_code": "R", "owning_unit": "unit-2"},
    )
    return _make([gated, _person(handling={"handling_code": "R"})], units=None)


async def test_fixed_handlings_naming_different_units_under_a_restricted_code_reject_the_row() -> (
    None
):
    rows = [{**_row("clash"), "flag": "x"}, {**_row("fine"), "flag": ""}]
    report, graph = await _run_recipe(_fixed_units_recipe(), rows)
    (rejection,) = report.rejections
    assert "different units under a restricted" in rejection.reason
    assert sorted(_titles(graph, "Person")) == ["fine"]


class FakeRules:
    """The slice of `RuleGate` `load_with_rules` uses: it holds the rows it is told to on the first
    pass and nothing on the second, as a pre-commit rule that cannot judge them does."""

    def __init__(self, hold_rows: tuple[int, ...] = ()) -> None:
        self.scheme = SCHEME
        self.investigation_id = "case-1"
        self._hold_rows = hold_rows
        self._passes = 0
        self.held: list[Any] = []
        self.last_written: list[Any] = []

    async def pre_commit(
        self, events: Any, tx: Any, *, load_id: str, unseen: Any, written: Any
    ) -> Any:
        from services.api.rule_evaluation import PreCommitVerdict

        self._passes += 1
        if self._passes == 1 and self._hold_rows:
            rule: Any = SimpleNamespace(id="rule-1")
            return PreCommitVerdict(hold={n: (rule, "cannot judge") for n in self._hold_rows})
        return PreCommitVerdict()

    async def after_commit(self, verdict: Any) -> None:
        return None

    async def hold(self, held: list[Any]) -> None:
        self.held.extend(held)

    async def record_expiries(self, written: Any) -> None:
        return None


async def _load_with(recipe: Recipe, rows: list[dict[str, str]], rules: FakeRules) -> Any:
    from services.api.studio_publish import load_with_rules

    graph = ValidatingGraph(ONTOLOGY)
    report, _events, _skipped = await load_with_rules(
        recipe,
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="l",
        investigation_scope="case-1",
        source="s.csv",
        rules=rules,  # type: ignore[arg-type]
    )
    return report, graph


async def test_a_no_binding_recipes_held_row_is_marked_by_its_elements_fixed_handling() -> None:
    recipe = _make(
        [_document(handling={"handling_code": "R", "owning_unit": "unit-2"})], units=None
    )
    rules = FakeRules(hold_rows=(0,))
    report, graph = await _load_with(recipe, [_row("held"), _row("loaded")], rules)
    (held,) = rules.held
    assert (held.handling.handling_code, held.handling.owning_unit) == ("R", "unit-2")
    assert sorted(_titles(graph)) == ["loaded"] and report.rows_held == 1


async def test_a_held_row_whose_marking_is_refused_is_a_rejection_and_nothing_is_lost_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.api import studio_publish
    from services.ingest.engine import RowRejected

    def refuse(recipe: Recipe, row: dict[str, str], scheme: Any) -> Handling:
        raise RowRejected("its elements' markings cannot be held as one marking")

    monkeypatch.setattr(studio_publish, "row_marking", refuse)
    recipe = _make([_document()], units=None)
    rules = FakeRules(hold_rows=(0,))
    report, graph = await _load_with(recipe, [_row("held"), _row("loaded")], rules)
    assert rules.held == []  # not held under any marking
    (rejection,) = report.rejections
    assert rejection.row_index == 0 and "cannot be held" in rejection.reason
    assert sorted(_titles(graph)) == ["loaded"] and graph.commits == 1
    assert report.rows_held == 0


# --- reasons name the part and the column, never the cell --------------------------------


def _shares_no_run_with(reason: str, cell: str, n: int = 4) -> bool:
    return not any(cell[i : i + n] in reason for i in range(len(cell) - n + 1))


@pytest.mark.parametrize(
    ("field", "cell"),
    [
        ("classification", "Zq9-Xyz"),
        ("handling_code", "Qw8-Xyz"),
        ("owning_unit", "Un7-Xyz"),
    ],
)
async def test_a_rejection_reason_names_the_part_and_column_not_the_cell(
    field: str, cell: str
) -> None:
    rows = [_row("odd", **{field: cell})]
    report, _ = await _run_recipe(_make([_document(handling=_bound(field))]), rows)
    (rejection,) = report.rejections
    assert cell not in rejection.reason and _shares_no_run_with(rejection.reason, cell)
    assert field.replace("_", " ") in rejection.reason and f"'{field}'" in rejection.reason


async def test_a_loosening_reason_names_the_part_and_column_not_the_cell() -> None:
    rows = [_row("loose", classification="OFFICIAL")]
    recipe = _make(
        [_document(handling=_bound("classification"))], defaults={"classification": "SECRET"}
    )
    report, _ = await _run_recipe(recipe, rows)
    (rejection,) = report.rejections
    assert "'OFFICIAL'" not in rejection.reason and _shares_no_run_with(
        rejection.reason, "OFFICIAL"
    )
    assert "classification" in rejection.reason and "looser" in rejection.reason


async def test_a_duplicate_groups_reason_names_no_cell() -> None:
    rows = [
        _row("same", handling_code="R", owning_unit="unit-1"),
        _row("same", handling_code="R", owning_unit="unit-2"),
    ]
    recipe = _make(
        [_document(handling=_bound("handling_code", "owning_unit"))], deduplicate=_by_title()
    )
    report, _ = await _run_recipe(recipe, rows)
    (rejection,) = report.rejections
    assert "'R'" not in rejection.reason


# --- the baseline check refuses what it cannot judge -------------------------------------


def test_a_fixed_handling_that_is_not_a_valid_marking_is_refused_with_its_cause() -> None:
    recipe = _make([_document(handling={"review_date": "not-a-date"})])
    (problem,) = recipe_rule_violations(
        recipe.row_template, ONTOLOGY, defaults_handling=recipe.defaults.handling, scheme=SCHEME
    )
    assert "review_date" in problem


# --- units are stripped at Connect -------------------------------------------------------


async def test_a_unit_entered_with_a_space_still_matches_its_cell() -> None:
    body = ConnectDraftInput(
        label="x",
        connector_profile="generic-csv",
        handling={**BASE, "units": [" unit-1", "unit-2 "]},
    )
    assert body.handling["units"] == ["unit-1", "unit-2"]
    defaults = RecipeDefaults.for_source(body.handling, None)
    recipe = _make([_document(handling=_bound("owning_unit"))], units=defaults.units)
    report, graph = await _run_recipe(recipe, [_row("ok", owning_unit="unit-1")])
    assert report.rejections == [] and sorted(_titles(graph)) == ["ok"]


# --- Connect declares which column carries each part -------------------------------------


def test_connect_validates_and_strips_the_declared_columns() -> None:
    body = ConnectDraftInput(
        label="x",
        connector_profile="generic-csv",
        handling={**BASE, "handling_columns": {"classification": " grade "}},
    )
    assert body.handling["handling_columns"] == {"classification": "grade"}
    for bad in (
        {"colour": "grade"},
        {"classification": ""},
        {"classification": "  "},
        ["grade"],
        "grade",
    ):
        with pytest.raises(ValidationError, match="handling_columns"):
            ConnectDraftInput(
                label="x",
                connector_profile="generic-csv",
                handling={**BASE, "handling_columns": bad},
            )


def test_the_declared_columns_reach_the_recipe_and_survive_a_patch() -> None:
    from services.api.studio_recipes import carry_source_declarations

    declared = {"classification": "grade"}
    old: dict[str, object] = {**BASE, "units": UNITS, "handling_columns": declared}
    defaults = RecipeDefaults.for_source(old, None)
    assert defaults.handling_columns == declared and "handling_columns" not in defaults.handling
    kept = carry_source_declarations(old, dict(BASE))
    assert kept == {**BASE, "units": UNITS, "handling_columns": declared}
    cleared = carry_source_declarations(old, {**BASE, "handling_columns": {}})
    assert cleared == {**BASE, "units": UNITS, "handling_columns": {}}


def test_a_binding_naming_a_column_not_declared_for_its_part_is_refused_at_save() -> None:
    recipe = _make([_document(handling=_bound("classification"))])
    declared = {"classification": "classification"}
    assert recipe_rule_violations(recipe.row_template, ONTOLOGY, handling_columns=declared) == []
    (problem,) = recipe_rule_violations(
        recipe.row_template, ONTOLOGY, handling_columns={"classification": "grade"}
    )
    assert "classification" in problem and "grade" in problem and "declared" in problem
    (problem,) = recipe_rule_violations(recipe.row_template, ONTOLOGY, handling_columns={})
    assert "classification" in problem and "declared" in problem


async def test_a_declared_column_the_source_lacks_rejects_the_row_at_run() -> None:
    recipe = _make([_document(handling={"classification": {"field": "grade"}})])
    recipe = recipe.model_copy(
        update={
            "defaults": recipe.defaults.model_copy(
                update={"handling_columns": {"classification": "grade"}}
            )
        }
    )
    report, graph = await _run_recipe(recipe, [_row("one")])
    (rejection,) = report.rejections
    assert "'grade'" in rejection.reason and "classification" in rejection.reason
    assert _titles(graph) == {}


def test_a_declared_column_the_source_lacks_is_refused_at_save() -> None:
    recipe = _make([_document(handling=_bound("classification"))])
    problems = recipe_rule_violations(
        recipe.row_template,
        ONTOLOGY,
        source_columns=["title"],
        handling_columns={"classification": "classification"},
    )
    assert any("declares 'classification' as the classification column" in p for p in problems)


# --- a declared column no element binds is refused ---------------------------------------


def test_a_declared_column_no_element_binds_is_refused_at_save() -> None:
    """Connect says a column carries classification and no element reads it: the source's SECRET
    rows would load at the default marking (rule 3), so the recipe is refused, naming both."""
    unbound = _make([_document()])
    declared = {"classification": "grade"}
    (problem,) = recipe_rule_violations(
        unbound.row_template, ONTOLOGY, handling_columns=declared, declared_columns=declared
    )
    assert (
        "element 'doc' does not bind classification, which the source declares in column 'grade'"
        in problem
    )
    bound = _make([_document(handling={"classification": {"field": "grade"}})])
    assert (
        recipe_rule_violations(
            bound.row_template, ONTOLOGY, handling_columns=declared, declared_columns=declared
        )
        == []
    )
    # A binding to another column does not stand in for the declared one.
    other = _make([_document(handling=_bound("classification"))])
    problems = recipe_rule_violations(other.row_template, ONTOLOGY, declared_columns=declared)
    assert len(problems) == 1 and "does not bind classification" in problems[0]


async def test_a_declared_column_no_element_binds_is_refused_at_run() -> None:
    recipe = _make([_document()])
    recipe = recipe.model_copy(
        update={
            "defaults": recipe.defaults.model_copy(
                update={"handling_columns": {"classification": "grade"}}
            )
        }
    )
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="does not bind classification"):
        await _run_recipe(recipe, [_row("one", classification="SECRET")], graph)
    assert graph.commits == 0 and graph.committed_nodes == []


# --- every element the row writes binds a declared column; a reference is exempt ---------


def _declared(recipe: Recipe, **columns: str) -> Recipe:
    return recipe.model_copy(
        update={"defaults": recipe.defaults.model_copy(update={"handling_columns": dict(columns)})}
    )


GRADE = {"classification": {"field": "grade"}}


def test_a_declared_column_every_written_element_must_bind_is_refused_at_save() -> None:
    entities = [
        _document(handling=GRADE),
        _person("person"),  # written, binds nothing: its rows would load at the default
    ]
    edges = [{"type": "MENTIONED_IN", "from": "person", "to": "doc"}]
    recipe = _make(entities, edges)
    declared = {"classification": "grade"}
    problems = recipe_rule_violations(recipe.row_template, ONTOLOGY, declared_columns=declared)
    assert any(
        p.startswith(
            "element 'person' does not bind classification, which the source declares in column"
            " 'grade'"
        )
        for p in problems
    )
    assert any("element 'MENTIONED_IN'" in p for p in problems)  # the link is written too


def test_a_referenced_entity_must_bind_a_declared_column_too() -> None:
    """`on_match: reference` is match-or-create: on a miss the node is created at its unbound
    marking, so a reference that does not bind is refused like any other element, at save and at
    run (the run half is the next test)."""
    declared = {"classification": "grade"}
    unbound = _person("person", match_on="family_name", on_match="reference")
    recipe = _make(
        [_document(handling=GRADE), unbound],
        [{"type": "MENTIONED_IN", "from": "person", "to": "doc", "handling": GRADE}],
    )
    (problem,) = recipe_rule_violations(recipe.row_template, ONTOLOGY, declared_columns=declared)
    assert "element 'person' does not bind classification" in problem
    bound = _person("person", match_on="family_name", on_match="reference", handling=GRADE)
    full = _make(
        [_document(handling=GRADE), bound],
        [{"type": "MENTIONED_IN", "from": "person", "to": "doc", "handling": GRADE}],
    )
    assert recipe_rule_violations(full.row_template, ONTOLOGY, declared_columns=declared) == []
    # An element with a `when` still has to bind.
    gated = _make(
        [_document(handling=GRADE), _person("person", when={"field": "x", "is": "not_null"})]
    )
    (problem,) = recipe_rule_violations(gated.row_template, ONTOLOGY, declared_columns=declared)
    assert "element 'person' does not bind classification" in problem


async def test_an_unbound_reference_is_refused_at_run() -> None:
    unbound = _person("person", match_on="family_name", on_match="reference")
    recipe = _declared(_make([_document(handling=GRADE), unbound]), classification="grade")
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="element 'person' does not bind classification"):
        await _run_recipe(recipe, [{**_row("one"), "grade": "SECRET"}], graph)
    assert graph.commits == 0 and graph.committed_nodes == []


async def test_a_reference_that_binds_creates_its_node_at_the_rows_marking_on_a_miss() -> None:
    recipe = _make(
        [_person("person", match_on="family_name", on_match="reference", handling=GRADE)]
    )
    report, graph = await _run_recipe(recipe, [{**_row("Newcomer"), "grade": "SECRET"}])
    assert report.rejections == []
    (node,) = _titles(graph, "Person").values()
    assert node.handling.classification == "SECRET"


async def test_a_reference_that_binds_keeps_the_stored_marking_on_a_match() -> None:
    recipe = _make(
        [_person("person", match_on="family_name", on_match="reference", handling=GRADE)]
    )
    graph = ValidatingGraph(ONTOLOGY)
    await _run_recipe(recipe, [{**_row("Known"), "grade": ""}], graph)
    report, graph = await _run_recipe(recipe, [{**_row("Known"), "grade": "SECRET"}], graph)
    assert report.rejections == [] and report.nodes_referenced == 1
    (node,) = _titles(graph, "Person").values()
    assert node.handling.classification == "OFFICIAL"  # matched, so not rewritten


async def test_a_declared_column_every_written_element_must_bind_is_refused_at_run() -> None:
    entities = [_document(handling=GRADE), _person("person")]
    recipe = _declared(
        _make(entities, [{"type": "MENTIONED_IN", "from": "person", "to": "doc"}]),
        classification="grade",
    )
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="element 'person' does not bind classification"):
        await _run_recipe(recipe, [{**_row("one"), "grade": "SECRET"}], graph)
    assert graph.commits == 0 and graph.committed_nodes == []


# --- Connect refuses a unit column with no units to name ---------------------------------


@pytest.mark.parametrize("part", ["originator", "owning_unit"])
def test_connect_refuses_a_declared_unit_column_when_there_are_no_units(part: str) -> None:
    for handling in (
        {**BASE, "handling_columns": {part: "unit"}},
        {**BASE, "units": [], "handling_columns": {part: "unit"}},
    ):
        with pytest.raises(ValidationError, match="units"):
            ConnectDraftInput(label="x", connector_profile="generic-csv", handling=handling)
    accepted = ConnectDraftInput(
        label="x",
        connector_profile="generic-csv",
        handling={**BASE, "units": UNITS, "handling_columns": {part: "unit"}},
    )
    assert accepted.handling["handling_columns"] == {part: "unit"}


# --- the held-marking block rolls back on anything but a refusal -------------------------


@pytest.mark.parametrize("target", ["merge_handling", "held_rows_for"])
async def test_an_unexpected_failure_computing_held_markings_rolls_the_load_back(
    target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api import studio_publish

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("unexpected")

    monkeypatch.setattr(studio_publish, target, boom)
    recipe = _make([_document(handling={"handling_code": "R"})], units=None)
    rules = FakeRules(hold_rows=(0,))
    graph = ValidatingGraph(ONTOLOGY)
    from services.api.studio_publish import load_with_rules

    with pytest.raises(ValueError, match="unexpected"):
        await load_with_rules(
            recipe,
            [_row("held"), _row("loaded")],
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="l",
            investigation_scope="case-1",
            source="s.csv",
            rules=rules,  # type: ignore[arg-type]
        )
    # The first pass was rolled back to hold the row; the second is rolled back here, not left
    # open: nothing was committed.
    assert graph.commits == 0 and graph.committed_nodes == [] and graph.rolled_back == 2


def test_a_patch_that_empties_the_units_a_kept_unit_column_needs_is_refused() -> None:
    """The kept `handling_columns` declare a unit column; the PATCH removes the units that column
    may name. The merged handling is judged as Connect judges one, so this is refused (and
    `update_draft`, which calls this before writing, stores nothing)."""
    from services.api.studio_recipes import (
        SourceDeclarationsInvalidError,
        carry_source_declarations,
    )

    old: dict[str, object] = {
        **BASE,
        "units": ["unit-1"],
        "handling_columns": {"owning_unit": "unit"},
    }
    with pytest.raises(SourceDeclarationsInvalidError, match="units"):
        carry_source_declarations(old, {**BASE, "units": []})
    # The same PATCH that keeps the units, or clears the declaration with them, is fine.
    assert carry_source_declarations(old, dict(BASE))["units"] == ["unit-1"]  # type: ignore[index]
    cleared = carry_source_declarations(old, {**BASE, "units": [], "handling_columns": {}})
    assert cleared == {**BASE, "units": [], "handling_columns": {}}


# --- two rows of one load writing the same link under different units --------------------


def _pair_recipe() -> Recipe:
    """Person `a` mentioned in Document `d`, both matched by reference, so two rows naming the same
    two values write the same link twice; the link's code and unit come from the row."""
    bound = _bound("handling_code", "owning_unit")  # on every element, so a row is one marking
    person = _person("a", match_on="family_name", on_match="reference", handling=bound)
    person["properties"] = {"family_name": {"field": "a"}}
    doc = _document(match_on="title", on_match="reference", handling=bound)
    doc["ref"] = "d"
    doc["properties"] = {"title": {"field": "d"}}
    edge = {"type": "MENTIONED_IN", "from": "a", "to": "d", "handling": bound}
    return _make([person, doc], [edge])


def _pair_row(code: str, unit: str, a: str = "Ada", d: str = "Dossier") -> dict[str, str]:
    return {"a": a, "d": d, "handling_code": code, "owning_unit": unit}


async def _merging(recipe: Recipe, rows: list[dict[str, str]]) -> tuple[Any, MergingGraph]:
    """A load into a store that merges as the real one does (ADR-102 Amendment 3)."""
    return await _run_recipe(recipe, rows, MergingGraph(ONTOLOGY))  # type: ignore[return-value]


def _links(graph: MergingGraph) -> list[tuple[str, str]]:
    return sorted((e.handling.owning_unit, e.handling.handling_code) for e in graph.committed_edges)


async def test_a_second_row_for_a_restricted_link_under_another_unit_is_a_link_of_its_own() -> None:
    """ADR-127 Amendment 2 rejected this row, because the store would have merged it into the first
    unit's link and shown it to that unit. The store no longer merges across audiences (ADR-102
    Amendment 3), so the row loads, as a link of its own that only its own unit reads."""
    rows = [
        _pair_row("R", "unit-1"),
        _pair_row("R", "unit-2"),  # the same pair, restricted, another unit
        _pair_row("R", "unit-2", a="Bea"),  # a different pair
    ]
    report, graph = await _merging(_pair_recipe(), rows)
    assert report.rejections == []
    assert _links(graph) == [("unit-1", "R"), ("unit-2", "R"), ("unit-2", "R")]
    ada = [e for e in graph.committed_edges if e.handling.owning_unit == "unit-2"]
    assert len({e.id for e in ada}) == 2
    assert len(report.created_edge_ids) == 3 and report.merged_edge_ids == []


async def test_a_dry_run_simulates_the_two_links_too() -> None:
    result = await dry_run_recipe(
        _pair_recipe(),
        [_pair_row("R", "unit-1"), _pair_row("R", "unit-2")],
        graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        source="s.csv",
        scheme=SCHEME,
    )
    assert result.rejections == []
    assert sorted((e.handling.owning_unit, e.occurrences) for e in result.edges) == [
        ("unit-1", 1),
        ("unit-2", 1),
    ]


async def test_a_dry_run_with_no_scheme_keys_a_link_on_a_form_it_can_hash() -> None:
    """Without a scheme no code is known to be restricted, which is how `audience_of` reads a code
    the scheme does not define: the key is the classification and code alone. The recipe binds no
    marking (a bound one is refused without a scheme), so every simulated link has one audience, and
    the same pair twice is one link of two occurrences, not a crash on an unhashable `Handling`."""
    person = _person("a", match_on="family_name", on_match="reference")
    person["properties"] = {"family_name": {"field": "a"}}
    doc = _document(match_on="title", on_match="reference")
    doc["ref"] = "d"
    doc["properties"] = {"title": {"field": "d"}}
    recipe = _make([person, doc], [{"type": "MENTIONED_IN", "from": "a", "to": "d"}])
    result = await dry_run_recipe(
        recipe,
        [_pair_row("P", "unit-1"), _pair_row("P", "unit-1"), _pair_row("P", "unit-1", a="Bea")],
        graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        source="s.csv",
    )
    assert result.rejections == []
    assert sorted(e.occurrences for e in result.edges) == [1, 2]


async def test_a_dry_run_still_merges_within_one_audience() -> None:
    result = await dry_run_recipe(
        _pair_recipe(),
        [_pair_row("R", "unit-1"), _pair_row("R", "unit-1"), _pair_row("P", "unit-1")],
        graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        source="s.csv",
        scheme=SCHEME,
    )
    assert sorted((e.handling.handling_code, e.occurrences) for e in result.edges) == [
        ("P", 1),
        ("R", 2),
    ]


async def test_one_restricted_link_among_two_is_a_link_of_its_own() -> None:
    rows = [_pair_row("P", "unit-1"), _pair_row("R", "unit-2")]
    report, graph = await _merging(_pair_recipe(), rows)
    assert report.rejections == []
    assert _links(graph) == [("unit-1", "P"), ("unit-2", "R")]


async def test_the_same_audience_merges_as_before() -> None:
    same_unit = [_pair_row("R", "unit-1"), _pair_row("R", "unit-1")]
    report, graph = await _merging(_pair_recipe(), same_unit)
    assert report.rejections == [] and len(graph.committed_edges) == 1
    assert len(report.created_edge_ids) == 1 and len(report.merged_edge_ids) == 0
    not_restricted = [_pair_row("P", "unit-1"), _pair_row("P", "unit-2")]
    report, graph = await _merging(_pair_recipe(), not_restricted)
    assert report.rejections == [] and len(graph.committed_edges) == 1  # units decide nothing


# --- the link check's gate and its identity key ------------------------------------------


def _fixed_split_recipe() -> Recipe:
    """No column is bound. Two sets of elements, mutually exclusive by `when`, each fixed to its
    own unit under `R` and each reaching the same two nodes by reference: rows of one set and rows
    of the other write one link between the same pair."""

    def fixed(unit: str) -> dict[str, Any]:
        return {"handling_code": "R", "owning_unit": unit, "originator": unit}

    entities: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for ref, flag, unit in (("1", "one", "unit-1"), ("2", "two", "unit-2")):
        when = {"field": "flag", "equals": flag}
        person = _person(
            f"a{ref}", match_on="family_name", on_match="reference", when=when, handling=fixed(unit)
        )
        person["properties"] = {"family_name": {"field": "a"}}
        doc = _document(match_on="title", on_match="reference", when=when, handling=fixed(unit))
        doc["ref"] = f"d{ref}"
        doc["properties"] = {"title": {"field": "d"}}
        entities += [person, doc]
        edges.append(
            {
                "type": "MENTIONED_IN",
                "from": f"a{ref}",
                "to": f"d{ref}",
                "when": when,
                "handling": fixed(unit),
            }
        )
    return _make(entities, edges)


async def test_a_recipe_that_binds_nothing_still_writes_each_units_link() -> None:
    rows = [
        {"flag": "one", "a": "Ada", "d": "Dossier"},
        {"flag": "two", "a": "Ada", "d": "Dossier"},
    ]
    recipe = _fixed_split_recipe()
    assert not any(e.handling and "field" in str(e.handling) for e in recipe.row_template.edges)
    report, graph = await _merging(recipe, rows)
    assert report.rejections == []
    assert sorted(e.handling.owning_unit for e in graph.committed_edges) == ["unit-1", "unit-2"]


def _ontology_with_a_numeric_match_key() -> Any:
    from schemas.domain import PropertyDef, PropertyType

    ontology = ONTOLOGY.model_copy(deep=True)
    asset = ontology.entity_type("Asset")
    assert asset is not None
    asset.properties.append(PropertyDef(name="serial", type=PropertyType.INTEGER))
    return ontology


def _asset_recipe() -> Recipe:
    bound = _bound("handling_code", "owning_unit")
    asset: dict[str, Any] = {
        "ref": "a",
        "pole_class": "object",
        "type": "Asset",
        "match_on": "serial",
        "on_match": "reference",
        "properties": {"serial": {"field": "s"}},
        "handling": bound,
    }
    doc = _document(match_on="title", on_match="reference", handling=bound)
    doc["ref"] = "d"
    doc["properties"] = {"title": {"field": "d"}}
    edge = {"type": "MENTIONED_IN", "from": "a", "to": "d", "handling": bound}
    return _make([asset, doc], [edge])


async def test_two_spellings_of_one_number_reach_one_node_and_each_units_row_is_its_own_link() -> None:
    from services.api.studio_publish import load_with_rules

    ontology = _ontology_with_a_numeric_match_key()
    rows = [
        {"s": "007", "d": "Dossier", "handling_code": "R", "owning_unit": "unit-1"},
        {"s": "7", "d": "Dossier", "handling_code": "R", "owning_unit": "unit-2"},
    ]
    graph = MergingGraph(ontology)
    report, _events, _held = await load_with_rules(
        _asset_recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ontology,
        load_id="l",
        investigation_scope="case-1",
        source="s.csv",
        rules=None,
        scheme=SCHEME,
    )
    assert report.rejections == []
    assert sorted(e.handling.owning_unit for e in graph.committed_edges) == ["unit-1", "unit-2"]
    assets = [n for n in graph.committed_nodes if n.type == "Asset"]
    assert len(assets) == 1  # "007" and "7" are one node


async def test_own_text_documents_matched_on_title_from_different_texts_are_not_one_node() -> None:
    from services.api.studio_publish import load_with_rules

    bound = _bound("handling_code", "owning_unit")
    person = _person("a", match_on="family_name", on_match="reference", handling=bound)
    person["properties"] = {"family_name": {"field": "a"}}
    doc = _document(match_on="title", on_match="reference", handling=bound)
    doc["ref"] = "d"
    doc["properties"] = {}  # no bound title: each Document's title is its text's first words
    doc["content"] = {"kind": "document_text", "field": "text"}
    edge = {"type": "MENTIONED_IN", "from": "a", "to": "d", "handling": bound}
    recipe = _make([person, doc], [edge])
    rows = [
        {"a": "Ada", "text": "The first report.", "handling_code": "R", "owning_unit": "unit-1"},
        {"a": "Ada", "text": "A different report.", "handling_code": "R", "owning_unit": "unit-2"},
    ]
    graph = ValidatingGraph(ONTOLOGY)
    report, _events, _held = await load_with_rules(
        recipe,
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="l",
        investigation_scope="case-1",
        source="s.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    assert report.rejections == []  # two Documents, so two links: no merge, no conflict
    assert len([n for n in graph.committed_nodes if n.type == "Document"]) == 2


async def test_a_dry_run_matches_an_own_text_document_on_the_key_the_run_uses() -> None:
    from services.api.studio_publish import load_with_rules

    doc = _document(match_on="title", on_match="reference")
    doc["properties"] = {}  # no bound title: the key is the text's first words
    doc["content"] = {"kind": "document_text", "field": "text"}
    recipe = _make([doc], units=None)

    async def counts(texts: list[str]) -> tuple[tuple[int, int], int]:
        rows = [{"text": t} for t in texts]
        dry = await dry_run_recipe(
            recipe,
            rows,
            graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=LOADER,
            source="s.csv",
            scheme=SCHEME,
        )
        graph = ValidatingGraph(ONTOLOGY)
        await load_with_rules(
            recipe,
            rows,
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id="l",
            investigation_scope="case-1",
            source="s.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
        )
        simulated = dry.entities_by_type["Document"]
        return (simulated.created, simulated.referenced), len(_titles(graph))

    # The same text twice is one Document, then a reference; different texts are two Documents.
    assert await counts(["The same report.", "The same report."]) == ((1, 1), 1)
    assert await counts(["The first report.", "A second report."]) == ((2, 0), 2)
