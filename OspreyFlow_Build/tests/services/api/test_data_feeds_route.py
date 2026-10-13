"""ADR-110 decision 9: the Glass's *Data feeds* — each pipeline feeding the case's datasets, its
schedule in words, next run and last outcome, so a reader sees how fresh the case's data is.
Viewer level and `read_data_feeds`; the case's recipes only; a run's counts only where the reader
may view the source (rule 3), as in the Admin area.

The recipe store and ledger are fakes holding to the real interfaces; `feeding` is proved live in
`test_studio_recipes_store.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_principal,
    get_recipe_runs,
    get_studio_recipes,
)
from services.api.recipe_runs import RecipeRun

from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.services.api.any_case import AnyCase

VIEWER = Principal(id="viewer-1", clearance="OFFICIAL", org_unit="unit-1", roles=["reports_viewer"],
                   datasets=["ds-case"])  # fmt: skip
NO_RIGHT = VIEWER.model_copy(update={"roles": ["source_author"]})
NOW = datetime(2026, 6, 2, 12, tzinfo=UTC)


def _handling(classification: str) -> dict[str, str]:
    return {"classification": classification, "handling_code": "P", "owning_unit": "unit-1",
            "originator": "unit-1"}  # fmt: skip


def _recipe(
    recipe_id: str, dataset: str, classification: str, cron: str | None
) -> StudioRecipeDraft:
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=recipe_id, version=1, status=StudioRecipeStatus.PUBLISHED,
        label=f"Feed {recipe_id}", handling=_handling(classification), owning_unit="unit-1",
        created_by="author-1", created_at=NOW, ready_for_profile=True, schedule_cron=cron,
        schedule_owner="approver-1" if cron else None, dataset_id=dataset,
    )  # fmt: skip


RECIPES = [
    _recipe("daily", "ds-case", "OFFICIAL", "0 6 * * *"),
    _recipe("secret", "ds-case", "SECRET", "0 7 * * *"),
    _recipe("by-hand", "ds-case", "OFFICIAL", None),
    _recipe("elsewhere", "ds-other", "OFFICIAL", "0 6 * * *"),
]


class _Recipes:
    async def feeding(self, dataset_ids: Sequence[str]) -> list[StudioRecipeDraft]:
        return [r for r in RECIPES if r.dataset_id in dataset_ids]


class _Runs:
    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
        source = Handling(**_handling("SECRET" if recipe_id == "secret" else "OFFICIAL"))
        return [RecipeRun(
            run_id=f"run-{recipe_id}", recipe_id=recipe_id, recipe_version=1,
            investigation_id="case-1", trigger="schedule", slot=NOW, run_as="approver-1",
            source=source, started_at=NOW, finished_at=NOW, outcome="succeeded", rows_read=40,
            nodes_created=12, nodes_referenced=3,
            edges_created=20, rows_rejected=0, rows_held=0, load_id="load-1", failure=None,
        )][:limit]  # fmt: skip


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
def client() -> Any:
    app.dependency_overrides[get_principal] = lambda: VIEWER
    app.dependency_overrides[get_studio_recipes] = _Recipes
    app.dependency_overrides[get_recipe_runs] = _Runs
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_case_feeds_are_listed_with_their_schedules_in_words(client: Any) -> None:
    feeds = {f["recipe_id"]: f for f in client.get("/v1/investigations/case-1/data-feeds").json()}
    assert set(feeds) == {"daily", "secret", "by-hand"}  # not the other case's dataset's
    assert feeds["daily"]["schedule"] == "every day at 06:00 (Europe/London)"
    assert feeds["daily"]["next_run"] is not None
    assert feeds["by-hand"]["schedule"] is None and feeds["by-hand"]["next_run"] is None
    assert feeds["daily"]["last_run"]["rows_read"] == 40


def test_a_feeds_counts_are_withheld_above_the_readers_clearance(client: Any) -> None:
    feeds = {f["recipe_id"]: f for f in client.get("/v1/investigations/case-1/data-feeds").json()}
    secret = feeds["secret"]["last_run"]
    assert secret["withheld"] is True and secret["outcome"] == "succeeded"
    assert secret["rows_read"] is None and secret["load_id"] is None


def test_an_account_without_read_data_feeds_is_refused(client: Any) -> None:
    app.dependency_overrides[get_principal] = lambda: NO_RIGHT
    response = client.get("/v1/investigations/case-1/data-feeds")
    assert response.status_code == 403
    assert response.json()["detail"]["right"] == "read_data_feeds"
