"""HTTP route wiring for Map (`docs/09_INGEST_STUDIO.md` §4) —
`/v1/ingest/transforms`, `PUT .../row-template`,
`GET .../map/sample-rows/{row_index}`, `POST .../map/handling-preview`.
Mirrors `test_studio_recipe_routes.py`'s own discipline: a fake store, no
live Postgres, and one access-control test per new read path
(`CLAUDE.md` rule 4).

Reuses `test_studio_recipe_routes.py`'s own `client` fixture rather than
duplicating its setup — pytest registers a fixture under the name it is
bound to in the *importing* module, so every test below takes it as a
`client` parameter same as that file does. Ruff's F811 doesn't know that a
same-named parameter isn't a redefinition of the module-level import, hence
the blanket suppression below rather than one `# noqa` per test."""
# ruff: noqa: F811, F401  (the imported `client` fixture is used only as every test's own same-named parameter)

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from services.api.app import app, get_principal

from knowledge_adapters import ARITY, REGISTRY
from tests.services.api.test_studio_recipe_routes import (
    _UNCLEARED_HANDLING,
    NO_ROLE_ANALYST,
    _draft,
    _ready_draft,
    _write_csv,
    client,
)


def _two_row_source(tmp_path: Path) -> str:
    return _write_csv(
        tmp_path,
        [
            {"a_party": "07960112334", "duration": "42"},
            {"a_party": "07468555891", "duration": "17"},
        ],
    )


# --- transforms ------------------------------------------------------------


def test_list_transforms_returns_the_whole_adapter_catalogue(client: TestClient) -> None:
    response = client.get("/v1/ingest/transforms")

    assert response.status_code == 200
    body = {t["name"]: t["arity"] for t in response.json()}
    assert set(body) == set(REGISTRY)
    # An adapter absent from `ARITY` takes a single `field` — arity 1.
    assert body["msisdn"] == 1
    assert body["grid_ref"] == ARITY["grid_ref"]


# --- row-template save ------------------------------------------------------


def _row_template_body(entity_overrides: dict[str, object] | None = None) -> dict[str, object]:
    entity: dict[str, object] = {
        "ref": "a",
        "pole_class": "object",
        "type": "Endpoint",
        "match_on": "value_normalised",
        "on_match": "reference",
        "properties": {},
    }
    if entity_overrides:
        entity.update(entity_overrides)
    return {"row_template": {"entities": [entity], "edges": []}, "unmapped_fields": []}


def test_put_row_template_as_source_author_succeeds(client: TestClient, tmp_path: Path) -> None:
    client.studio_recipes.draft = _ready_draft(tmp_path)  # type: ignore[attr-defined]

    response = client.put("/v1/ingest/recipes/recipe-1/row-template", json=_row_template_body())

    assert response.status_code == 200
    assert response.json()["row_template"]["entities"][0]["ref"] == "a"


def test_put_row_template_before_profile_has_run_is_a_conflict(client: TestClient) -> None:
    """§3: "the studio does not let you map until it has run" — a draft
    that hasn't cleared Connect's own gates yet (`ready_for_profile`) can't
    reach Map's save either."""
    client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]

    response = client.put("/v1/ingest/recipes/recipe-1/row-template", json=_row_template_body())

    assert response.status_code == 409
    assert response.json()["error"] == "recipe_not_ready_for_profile"


def test_put_row_template_without_the_source_author_role_is_forbidden(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(tmp_path)  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST

    response = client.put("/v1/ingest/recipes/recipe-1/row-template", json=_row_template_body())

    assert response.status_code == 403


def test_put_row_template_for_a_recipe_in_a_different_unit_is_not_found(client: TestClient) -> None:
    client.studio_recipes.draft = _draft(owning_unit="unit-2")  # type: ignore[attr-defined]

    response = client.put("/v1/ingest/recipes/recipe-1/row-template", json=_row_template_body())

    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"


def test_put_row_template_rejects_an_element_override_that_loosens_classification(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        handling={
            "classification": "OFFICIAL-SENSITIVE",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
    )

    response = client.put(
        "/v1/ingest/recipes/recipe-1/row-template",
        json=_row_template_body({"handling": {"classification": "OFFICIAL"}}),
    )

    assert response.status_code == 422
    assert response.json()["error"] == "handling_loosened"


def test_put_row_template_allows_an_element_override_that_tightens_classification(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path,
        handling={
            "classification": "OFFICIAL-SENSITIVE",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
    )

    response = client.put(
        "/v1/ingest/recipes/recipe-1/row-template",
        json=_row_template_body({"handling": {"classification": "SECRET"}}),
    )

    assert response.status_code == 200


# --- sample-row scrubbing ----------------------------------------------------


def test_get_sample_row_returns_unmasked_values_for_a_cleared_principal(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, source_location=_two_row_source(tmp_path)
    )

    response = client.get("/v1/ingest/recipes/recipe-1/map/sample-rows/1")

    assert response.status_code == 200
    body = response.json()
    assert body["values_masked"] is False
    assert body["values"]["a_party"] == "07468555891"
    assert body["is_last_row"] is True


def test_get_sample_row_masks_values_for_a_principal_who_cannot_clear_the_source(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, handling=_UNCLEARED_HANDLING, source_location=_two_row_source(tmp_path)
    )

    response = client.get("/v1/ingest/recipes/recipe-1/map/sample-rows/0")

    assert response.status_code == 200
    body = response.json()
    assert body["values_masked"] is True
    assert body["values"]["a_party"] == "#" * len("07960112334")


def test_get_sample_row_masks_a_free_text_column_with_a_summary_not_a_positional_mask(
    client: TestClient, tmp_path: Path
) -> None:
    """`_is_free_text_column` (`services/ingest/profiler.py`) classes a
    long, pattern-free string column as free text, so masking it must go
    through `_free_text_summary` rather than `_shape_mask` — the exact
    branch a missing import once made unreachable in every other test
    here (neither of `_two_row_source`'s columns are free text)."""
    source = _write_csv(
        tmp_path,
        [{"notes": "the quick brown fox jumps over the lazy dog near the old stone bridge"}],
    )
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, handling=_UNCLEARED_HANDLING, source_location=source
    )

    response = client.get("/v1/ingest/recipes/recipe-1/map/sample-rows/0")

    assert response.status_code == 200
    body = response.json()
    assert body["values_masked"] is True
    assert body["values"]["notes"].startswith("free text —")


def test_get_sample_row_past_the_sample_is_not_found(client: TestClient, tmp_path: Path) -> None:
    client.studio_recipes.draft = _ready_draft(tmp_path)  # type: ignore[attr-defined]

    response = client.get("/v1/ingest/recipes/recipe-1/map/sample-rows/5")

    assert response.status_code == 404
    assert response.json()["error"] == "row_index_out_of_range"


def test_get_sample_row_for_a_recipe_in_a_different_unit_is_not_found(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, owning_unit="unit-2"
    )

    response = client.get("/v1/ingest/recipes/recipe-1/map/sample-rows/0")

    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"


# --- handling/provenance preview ---------------------------------------------


def test_preview_handling_reflects_an_unsaved_override(client: TestClient, tmp_path: Path) -> None:
    client.studio_recipes.draft = _ready_draft(tmp_path)  # type: ignore[attr-defined]

    response = client.post(
        "/v1/ingest/recipes/recipe-1/map/handling-preview",
        json={"row_index": 0, "handling_override": {"classification": "SECRET"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["handling"]["classification"] == "SECRET"
    # Untouched fields still come from the draft's own Connect-stage handling.
    assert body["handling"]["originator"] == "unit-1"
    assert body["provenance"]["state"] == "asserted"


def test_preview_handling_for_a_recipe_in_a_different_unit_is_not_found(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, owning_unit="unit-2"
    )

    response = client.post(
        "/v1/ingest/recipes/recipe-1/map/handling-preview",
        json={"row_index": 0},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"
