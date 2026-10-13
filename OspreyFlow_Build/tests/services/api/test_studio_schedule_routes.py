"""ADR-110 decision 7: what the Studio's structured schedule editor asks of the Conduit.

- **A preview before saving**: the schedule in words and its next five runs, or the refusal in words
  — the same `validate_schedule`/`due_slots` the executor keeps, so the editor cannot promise a
  schedule the executor would run differently.
- **Pause and Resume** by the source approver (`schedule_pipelines`), audited.
- **The recipe's run history**, its counts withheld above the reader's clearance as everywhere else.

Fakes hold to the real stores' interfaces; the stores themselves are proved live elsewhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
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

from tests.services.api.any_case import AnyCase

CASE = "/v1/investigations/inv-1/ingest/recipes"
APPROVER = Principal(id="approver-1", clearance="OFFICIAL", org_unit="unit-1",
                     roles=["source_approver", "reports_viewer"])  # fmt: skip
AUTHOR = Principal(id="author-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_author"])
NOW = datetime(2026, 6, 2, 12, tzinfo=UTC)
HANDLING = {"classification": "SECRET", "handling_code": "P", "owning_unit": "unit-1",
            "originator": "unit-1"}  # fmt: skip


class _Recipes:
    def __init__(self) -> None:
        self.draft = StudioRecipeDraft(  # type: ignore[call-arg]
            recipe_id="recipe-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Feed",
            handling=HANDLING, owning_unit="unit-1", created_by="author-1", created_at=NOW,
            ready_for_profile=True, schedule_cron="0 6 * * *", schedule_owner="approver-1",
        )  # fmt: skip

    async def get_authorized(self, recipe_id: str, principal: Principal) -> StudioRecipeDraft:
        return self.draft

    async def get(self, recipe_id: str) -> StudioRecipeDraft:
        return self.draft

    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None:
        self.draft = self.draft.model_copy(
            update={"schedule_paused": paused, "schedule_paused_reason": reason if paused else None}
        )


class _Runs:
    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
        return [RecipeRun(
            run_id="r1", recipe_id=recipe_id, recipe_version=1, investigation_id="inv-1",
            trigger="schedule", slot=NOW, run_as="approver-1", source=Handling(**HANDLING),
            started_at=NOW, finished_at=NOW, outcome="succeeded", rows_read=9, nodes_created=1,
            nodes_referenced=0, edges_created=0, rows_rejected=0, rows_held=0, load_id="l",
            failure=None,
        )]  # fmt: skip


class _Audit:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    async def record(self, **kwargs: Any) -> None:
        self.actions.append((kwargs["action"], kwargs["principal"].id))


@pytest.fixture
def client() -> Any:
    recipes, audit = _Recipes(), _Audit()
    app.dependency_overrides[get_principal] = lambda: APPROVER
    app.dependency_overrides[get_studio_recipes] = lambda: recipes
    app.dependency_overrides[get_recipe_runs] = _Runs
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    test_client = TestClient(app)
    test_client.recipes, test_client.audit = recipes, audit  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def test_a_preview_gives_the_schedule_in_words_and_its_next_five_runs(client: Any) -> None:
    response = client.post(
        "/v1/ingest/schedule-preview",
        json={"cron": "0 6 * * 1-5", "timezone": "Europe/London", "after": "2026-06-05T12:00:00Z"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["words"] == "every weekday at 06:00 (Europe/London)"
    assert body["next_runs"] == [
        "2026-06-08T05:00:00Z", "2026-06-09T05:00:00Z", "2026-06-10T05:00:00Z",
        "2026-06-11T05:00:00Z", "2026-06-12T05:00:00Z",
    ]  # fmt: skip


def test_a_preview_of_a_schedule_it_could_not_keep_is_refused_in_words(client: Any) -> None:
    response = client.post("/v1/ingest/schedule-preview", json={"cron": "*/5 * * * *"})
    assert response.status_code == 422
    assert "more often than every 15 minutes" in response.json()["detail"]


def test_the_source_approver_pauses_and_resumes_it_audited(client: Any) -> None:
    paused = client.post(f"{CASE}/recipe-1/schedule/pause")
    assert paused.status_code == 200 and paused.json()["schedule_paused"] is True
    assert paused.json()["schedule_paused_reason"] == "paused by approver-1"
    resumed = client.post(f"{CASE}/recipe-1/schedule/resume")
    assert resumed.status_code == 200 and resumed.json()["schedule_paused"] is False
    assert client.audit.actions == [
        ("pause_recipe_schedule", "approver-1"), ("resume_recipe_schedule", "approver-1"),
    ]  # fmt: skip


def test_an_author_cannot_pause_a_schedule(client: Any) -> None:
    app.dependency_overrides[get_principal] = lambda: AUTHOR
    assert client.post(f"{CASE}/recipe-1/schedule/pause").status_code == 403
    assert client.recipes.draft.schedule_paused is False


def test_the_recipes_runs_are_listed_with_counts_withheld_above_the_reader(client: Any) -> None:
    (run,) = client.get(f"{CASE}/recipe-1/runs").json()
    assert run["outcome"] == "succeeded" and run["withheld"] is True and run["rows_read"] is None


@pytest.mark.parametrize(
    ("dataset", "watch", "words"),
    [
        ("carrier-b", "in/*.csv", "no folder"),
        ("carrier-b", "", "a filename pattern"),
        (None, "*.csv", "belongs to no dataset"),
    ],
    ids=["folder-part", "empty", "no-dataset"],
)
def test_a_watch_it_could_not_keep_is_refused_in_words_and_nothing_saved(
    client: Any, tmp_path: Any, dataset: str | None, watch: str, words: str
) -> None:
    """ADR-110 Amendment 4, point 1. The route's other dependencies are stand-ins: the refusal
    comes before either is used."""
    from services.api.app import get_ontology, get_recipes_repo_root

    app.dependency_overrides[get_ontology] = object
    app.dependency_overrides[get_recipes_repo_root] = lambda: tmp_path
    client.recipes.draft = client.recipes.draft.model_copy(update={"dataset_id": dataset})
    response = client.patch(f"{CASE}/recipe-1/schedule", json={"schedule_watch": watch})
    assert response.status_code == 422
    assert words in response.json()["detail"]
    assert client.recipes.draft.schedule_watch is None
