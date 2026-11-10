"""The Studio's Test (Verify) judges the deployment's marking ceiling (ADR-148 decision 10;
studio-b's L1.10b, item 3), so a file above it is told before Load, in the same words as the
load's refusal.

Until L1.10b only the load judged it (`engine.run_recipe`): Test could pass a file the run then
refused. Now `engine.dry_run_recipe` judges the rows it runs as `run_recipe` judges every row, and
Verify judges every row of the file on a pipeline without steps, not only its sample. A staged
pipeline is judged over the rows Test runs, after its steps.

What a mistake would do, and the case that catches it:
- Test passing a file with a row above the ceiling —
  `test_test_refuses_a_file_with_a_row_above_the_ceiling_in_the_load_s_words`;
- Test judging only its sample, so a row past it goes untold until Load —
  `test_test_judges_every_row_of_the_file_not_only_its_sample`;
- a staged pipeline's Test passing it —
  `test_a_staged_pipeline_s_test_refuses_a_row_above_the_ceiling`;
- the check refusing what is at the ceiling, or anything with no ceiling set —
  `test_test_passes_a_file_at_the_ceiling` and `test_with_no_ceiling_set_test_passes_as_before`.

Synthetic rows (rule 9).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_principal
from services.ingest.ceiling import CEILING_ENV, AboveTheDeploymentCeiling
from services.ingest.profiler import DEFAULT_SAMPLE_SIZE

from schemas.ingest import FieldBinding, RecipeEntity, RowTemplate
from tests.services.api.test_studio_recipe_routes import SOURCE_AUTHOR, _ready_draft
from tests.services.api.test_studio_staging_routes import (  # noqa: F401  (fixtures)
    RECIPE_URL,
    _one_hidden_row,
    staged,
    store,
)
from tests.services.api.test_studio_verify_routes import (  # noqa: F401  (fixtures)
    client,
    graph_client,
)

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

#: The load's own words for this refusal, at an OFFICIAL ceiling.
LOAD_WORDS = AboveTheDeploymentCeiling("OFFICIAL").problems[0]
CLEARED = SOURCE_AUTHOR.model_copy(update={"clearance": "SECRET"})


def _template() -> RowTemplate:
    """One Endpoint per row, its classification read from the row's `cls`."""
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a", pole_class="object", type="Endpoint", on_match="create",
                properties={
                    "value_normalised": FieldBinding(field="a_party"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
                handling={"classification": {"field": "cls"}},
            )
        ]
    )  # fmt: skip


def _file(tmp_path: Path, markings: list[str]) -> str:
    path = tmp_path / "source.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["a_party", "cls"])
        writer.writeheader()
        writer.writerows(
            {"a_party": f"0796011{i:05d}", "cls": marking} for i, marking in enumerate(markings)
        )
    return str(path)


def _verify(client: TestClient, tmp_path: Path, markings: list[str]) -> object:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, source_location=_file(tmp_path, markings), row_template=_template()
    )
    return client.post(f"{RECIPE_URL}/verify")


def test_test_refuses_a_file_with_a_row_above_the_ceiling_in_the_load_s_words(
    graph_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    app.dependency_overrides[get_principal] = lambda: CLEARED
    response = _verify(graph_client, tmp_path, ["OFFICIAL", "SECRET", "OFFICIAL"])
    assert response.status_code == 422, response.text  # type: ignore[attr-defined]
    body = response.json()  # type: ignore[attr-defined]
    assert body["error"] == "above_the_deployments_highest_marking", body
    assert body["detail"] == LOAD_WORDS
    assert "0796011" not in response.text  # type: ignore[attr-defined]


def test_test_judges_every_row_of_the_file_not_only_its_sample(
    graph_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row past the sample is the only one above the ceiling, and the author is cleared only to
    OFFICIAL, as the sample is: Test is not withheld, and still tells the ceiling."""
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    response = _verify(graph_client, tmp_path, ["OFFICIAL"] * DEFAULT_SAMPLE_SIZE + ["SECRET"])
    assert response.status_code == 422, response.text  # type: ignore[attr-defined]
    assert response.json()["detail"] == LOAD_WORDS  # type: ignore[attr-defined]


def test_test_passes_a_file_at_the_ceiling(
    graph_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL-SENSITIVE")
    app.dependency_overrides[get_principal] = lambda: CLEARED
    response = _verify(graph_client, tmp_path, ["OFFICIAL", "OFFICIAL-SENSITIVE"])
    assert response.status_code == 200, response.text  # type: ignore[attr-defined]


def test_with_no_ceiling_set_test_passes_as_before(
    graph_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CEILING_ENV, raising=False)
    app.dependency_overrides[get_principal] = lambda: CLEARED
    response = _verify(graph_client, tmp_path, ["OFFICIAL", "SECRET"])
    assert response.status_code == 200, response.text  # type: ignore[attr-defined]


def test_a_staged_pipeline_s_test_refuses_a_row_above_the_ceiling(
    staged: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    app.dependency_overrides[get_principal] = lambda: CLEARED.model_copy(
        update={"datasets": ["pid"]}
    )
    _one_hidden_row(staged, tmp_path, "SECRET")
    response = staged.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == LOAD_WORDS
    assert "OKAFOR" not in response.text  # the SECRET booking's visitor
