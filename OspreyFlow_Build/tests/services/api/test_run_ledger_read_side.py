"""ADR-127 decision 6, rules 3, 4 and 7: the run ledger now keeps, beside each run, a record of the
node and link ids the load created and the existing links it merged into. Those are ids of elements
some readers may not see, so no route that shows a run may return one, nor a count taken from them.

Every route that returns ledger rows is asked here, as a reader who may view the source (whose
counts are shown) and as one who may not: the Studio's `/runs`, the Admin area's
`/v1/admin/schedules/{id}/runs`, and the Glass's `/data-feeds`. The store's fake hands back rows
holding to the real interface, and also offers the record itself, so a route that fetched it would
have something to return. No route does: `RecipeRun`, the one shape a route reads, has no record
field and the store's column list does not select one, which the structural cases pin."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import recipe_runs
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
from schemas.admin import ScheduleRunView
from schemas.domain import Handling, Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.services.api.any_case import AnyCase

NOW = datetime(2026, 6, 2, 12, tzinfo=UTC)
#: Ids and a count only the record holds. None may appear in any response.
SECRET_IDS = ["node-secret-1", "edge-created-secret-1", "edge-merged-secret-1"]
HANDLING = {"classification": "SECRET", "handling_code": "P", "owning_unit": "unit-1",
            "originator": "unit-1"}  # fmt: skip
# The Admin route's right comes with the administrator role, the others' with the viewer's.
OFFICIAL_READER = Principal(id="viewer-1", clearance="OFFICIAL", org_unit="unit-1",
                            roles=["source_approver", "reports_viewer", "osprey-admin"],
                            datasets=["ds-case"])  # fmt: skip
SECRET_READER = OFFICIAL_READER.model_copy(update={"id": "viewer-2", "clearance": "SECRET"})


def _draft() -> StudioRecipeDraft:
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id="recipe-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Feed",
        handling=HANDLING, owning_unit="unit-1", created_by="author-1", created_at=NOW,
        ready_for_profile=True, schedule_cron="0 6 * * *", schedule_owner="approver-1",
        dataset_id="ds-case",
    )  # fmt: skip


class _Recipes:
    async def get_authorized(self, recipe_id: str, principal: Principal) -> StudioRecipeDraft:
        return _draft()

    async def get(self, recipe_id: str) -> StudioRecipeDraft:
        return _draft()

    async def feeding(self, dataset_ids: Any) -> list[StudioRecipeDraft]:
        return [_draft()]

    async def scheduled(self) -> list[StudioRecipeDraft]:
        return [_draft()]


class _Runs:
    """Holds to `RecipeRunStore`: what it returns is `RecipeRun`s. It also has the record, in the
    one place a route could reach it, so a leak would have something to leak."""

    record = {"created_node_ids": SECRET_IDS[:1], "created_edge_ids": SECRET_IDS[1:2],
              "merged_edge_ids": SECRET_IDS[2:]}  # fmt: skip

    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
        return [RecipeRun(
            run_id="run-1", recipe_id=recipe_id, recipe_version=1, investigation_id="inv-1",
            trigger="schedule", slot=NOW, run_as="approver-1", source=Handling(**HANDLING),
            started_at=NOW, finished_at=NOW, outcome="succeeded", rows_read=9, nodes_created=1,
            nodes_referenced=0, edges_created=1, rows_rejected=0, rows_held=0, load_id="l",
            failure=None,
        )][:limit]  # fmt: skip

    async def load_record(self, load_id: str) -> dict[str, Any]:
        return self.record


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
def client() -> Any:
    app.dependency_overrides[get_studio_recipes] = _Recipes
    app.dependency_overrides[get_recipe_runs] = _Runs
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    yield TestClient(app)
    app.dependency_overrides.clear()


ROUTES = [
    "/v1/investigations/inv-1/ingest/recipes/recipe-1/runs",
    "/v1/admin/schedules/recipe-1/runs",
    "/v1/investigations/inv-1/data-feeds",
]


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize("reader", [OFFICIAL_READER, SECRET_READER], ids=["official", "secret"])
def test_no_ledger_route_returns_an_id_from_the_record(client: Any, path: str, reader: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: reader
    response = client.get(path)
    assert response.status_code == 200, response.text
    for secret in SECRET_IDS:
        assert secret not in response.text
    for word in ("created_node_ids", "created_edge_ids", "merged_edge_ids", "load_records"):
        assert word not in response.text


@pytest.mark.parametrize("path", ROUTES[:2])
def test_a_reader_who_may_not_view_the_source_is_given_no_counts_at_all(client: Any, path: str) -> None:
    app.dependency_overrides[get_principal] = lambda: OFFICIAL_READER
    (run,) = client.get(path).json()
    assert run["withheld"] is True
    assert run["rows_read"] is None and run["nodes_created"] is None and run["edges_created"] is None


def test_the_one_shape_a_route_reads_has_no_record_field() -> None:
    """If `RecipeRun` gained the record, every route that builds a view from it would be one edit
    from returning it; the column list is what the store selects."""
    assert not {n for n in RecipeRun.model_fields if "record" in n or "edge_ids" in n or "node_ids" in n}
    assert "load_record" not in recipe_runs._COLUMNS
    assert not {n for n in ScheduleRunView.model_fields if "record" in n or "_ids" in n}
