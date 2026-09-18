"""Per-element `handling`/`provenance` overrides — `docs/09_INGEST_STUDIO.md`
§4: "The per-element override this paragraph promises is not yet a field...
building it is this stage's own scope." Pure-function coverage only
(`services/ingest/engine.py`'s `_merge_override`/`preview_handling_and_provenance`
need no `GraphPort`, no ArcadeDB) — `test_recipe_engine_end_to_end.py`
already covers the write path end to end against a live ArcadeDB; this file
covers the merge logic itself in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.ingest.engine import _merge_override, preview_handling_and_provenance

from schemas.ingest import Recipe, RecipeConnector, RecipeDefaults, RecipeEntity, RowTemplate

DEFAULTS_HANDLING = {
    "classification": "OFFICIAL-SENSITIVE",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def _recipe() -> Recipe:
    return Recipe(
        id="recipe-1",
        version=1,
        label="Carrier A",
        connector=RecipeConnector(profile="generic-csv"),
        ontology_version=1,
        defaults=RecipeDefaults(handling=DEFAULTS_HANDLING, provenance={}),
        row_template=RowTemplate(entities=[]),
    )


def test_merge_override_is_a_no_op_with_no_override() -> None:
    assert _merge_override(DEFAULTS_HANDLING, None) == DEFAULTS_HANDLING


def test_merge_override_lets_override_win_per_key() -> None:
    merged = _merge_override(DEFAULTS_HANDLING, {"classification": "SECRET"})

    assert merged["classification"] == "SECRET"
    # Untouched keys still come from the defaults.
    assert merged["originator"] == "unit-1"


def test_preview_handling_and_provenance_with_no_override_matches_recipe_defaults() -> None:
    recipe = _recipe()

    handling, provenance = preview_handling_and_provenance(
        recipe, source="s3://bucket/a.csv", row_index=0, now=datetime.now(UTC)
    )

    assert handling.classification == "OFFICIAL-SENSITIVE"
    assert provenance.state.value == "asserted"


def test_preview_handling_and_provenance_applies_an_element_override() -> None:
    recipe = _recipe()

    handling, provenance = preview_handling_and_provenance(
        recipe,
        source="s3://bucket/a.csv",
        row_index=0,
        now=datetime.now(UTC),
        handling_override={"classification": "SECRET"},
        provenance_override={"state": "inferred"},
    )

    assert handling.classification == "SECRET"
    # An override field the element didn't touch still comes from defaults.
    assert handling.originator == "unit-1"
    assert provenance.state.value == "inferred"


def test_recipe_entity_handling_and_provenance_default_to_none() -> None:
    """A `RecipeEntity`/`RecipeEdge` with no override at all — the common
    case — carries `None`, not an empty dict, so `_merge_override` treats it
    as exactly a no-op rather than an override that happens to be empty."""
    entity = RecipeEntity(ref="a", pole_class="object", type="Endpoint")

    assert entity.handling is None
    assert entity.provenance is None
