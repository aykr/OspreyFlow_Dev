"""The Admin area's *Schedules and runs* routes (ADR-110 decision 8, Amendment 2): every scheduled
recipe across the deployment, behind `operate_schedules`, every action audited with the
administrator named.

**Rule 3 in the console.** An administrator sees each schedule's metadata and outcomes, but a run's
counts only where the source's handling is one they may view — otherwise *withheld*. The failure's
words are withheld with them *(mine)*: a failure can name what the source holds (a file, a field).

The recipe store and ledger are fakes holding to the real ones' interfaces; both stores' own reads
are proved live in `test_studio_recipes_store.py` and `test_recipe_runs.py`. What is under test here
is the route's withholding and gating.
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
    get_principal,
    get_recipe_runs,
    get_recipes_repo_root,
    get_schedule_executor,
    get_studio_recipes,
)
from services.api.recipe_runs import RecipeRun
from services.api.scheduler import ScheduleRunRefused

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-9", roles=["osprey-admin"])
ANALYST = Principal(id="analyst-1", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
NOW = datetime(2026, 6, 2, 12, tzinfo=UTC)


def _handling(classification: str) -> dict[str, str]:
    return {"classification": classification, "handling_code": "P", "owning_unit": "unit-1",
            "originator": "unit-1"}  # fmt: skip


def _recipe(recipe_id: str, classification: str) -> StudioRecipeDraft:
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=recipe_id, version=1, status=StudioRecipeStatus.PUBLISHED,
        label=f"Feed {recipe_id}",
        handling=_handling(classification), owning_unit="unit-1", created_by="author-1",
        created_at=NOW, ready_for_profile=True, schedule_cron="0 6 * * 1-5",
        schedule_timezone="Europe/London", schedule_owner="approver-1", schedule_set_at=NOW,
        schedule_case="case-1",
    )  # fmt: skip


def _run(recipe_id: str, classification: str) -> RecipeRun:
    return RecipeRun(
        run_id=f"run-{recipe_id}", recipe_id=recipe_id, recipe_version=1, investigation_id="case-1",
        trigger="schedule", slot=NOW, run_as="approver-1",
        source=Handling(**_handling(classification)), started_at=NOW, finished_at=NOW,
        outcome="failed", rows_read=40, nodes_created=12, nodes_referenced=3, edges_created=20,
        rows_rejected=1, rows_held=0, load_id="load-1", failure="KeyError: 'informant_name'",
    )  # fmt: skip


class _Recipes:
    def __init__(self) -> None:
        self.held = [_recipe("open", "OFFICIAL"), _recipe("secret", "SECRET")]
        self.paused: dict[str, str | None] = {}

    async def scheduled(self) -> list[StudioRecipeDraft]:
        return [
            r.model_copy(
                update={"schedule_paused": True, "schedule_paused_reason": self.paused[r.recipe_id]}
            )
            if r.recipe_id in self.paused else r
            for r in self.held
        ]  # fmt: skip

    async def set_paused(self, recipe_id: str, *, paused: bool, reason: str | None) -> None:
        if paused:
            self.paused[recipe_id] = reason
        else:
            self.paused.pop(recipe_id, None)

    async def retime(self, recipe_id: str, *, cron: str, timezone: str, now: datetime) -> None:
        self.held = [
            r.model_copy(update={"schedule_cron": cron, "schedule_timezone": timezone,
                                 "schedule_set_at": now})
            if r.recipe_id == recipe_id else r
            for r in self.held
        ]  # fmt: skip


class _Executor:
    """Stands in for `ScheduleExecutor.run_now`, refusing as it does (in words)."""

    def __init__(self) -> None:
        self.ran: list[str] = []
        self.refuse: str | None = None

    async def run_now(self, recipe: StudioRecipeDraft) -> None:
        if self.refuse:
            raise ScheduleRunRefused(self.refuse)
        self.ran.append(recipe.recipe_id)


class _Runs:
    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
        return [_run(recipe_id, "SECRET" if recipe_id == "secret" else "OFFICIAL")][:limit]


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


@pytest.fixture
def client(tmp_path: Any) -> Any:
    recipes, audit, executor = _Recipes(), _Audit(), _Executor()
    app.dependency_overrides[get_schedule_executor] = lambda: executor
    # These recipes carry no mapping, so there is no YAML to re-commit (`_commit_schedule`).
    app.dependency_overrides[get_recipes_repo_root] = lambda: tmp_path
    app.dependency_overrides[get_principal] = lambda: ADMIN
    app.dependency_overrides[get_studio_recipes] = lambda: recipes
    app.dependency_overrides[get_recipe_runs] = lambda: _Runs()
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    test_client = TestClient(app)
    test_client.recipes, test_client.audit = recipes, audit  # type: ignore[attr-defined]
    test_client.executor = executor  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def test_every_schedule_is_listed_in_words_with_its_owner_case_and_next_run(client: Any) -> None:
    listed = {s["recipe_id"]: s for s in client.get("/v1/admin/schedules").json()}
    assert set(listed) == {"open", "secret"}
    open_ = listed["open"]
    assert open_["schedule"] == "every weekday at 06:00 (Europe/London)"
    assert (open_["owner"], open_["case_id"]) == ("approver-1", "case-1")
    assert open_["label"] == "Feed open"
    assert open_["next_run"] is not None and open_["paused"] is False
    assert open_["last_run"]["outcome"] == "failed"


def test_a_runs_counts_and_failure_are_withheld_above_the_administrators_clearance(
    client: Any,
) -> None:
    listed = {s["recipe_id"]: s for s in client.get("/v1/admin/schedules").json()}
    shown, withheld = listed["open"]["last_run"], listed["secret"]["last_run"]
    assert shown["withheld"] is False and shown["rows_read"] == 40
    assert shown["failure"] == "KeyError: 'informant_name'"
    assert withheld["withheld"] is True and withheld["outcome"] == "failed"
    for name in ("rows_read", "nodes_created", "nodes_referenced", "edges_created",
                 "rows_rejected", "rows_held", "load_id", "failure"):  # fmt: skip
        assert withheld[name] is None, name
    history = client.get("/v1/admin/schedules/secret/runs").json()
    assert history and all(r["withheld"] and r["rows_read"] is None for r in history)


def test_pause_and_resume_are_audited_with_the_administrator_named(client: Any) -> None:
    paused = client.post("/v1/admin/schedules/open/pause", json={"reason": "source moving"})
    assert paused.status_code == 200 and paused.json()["paused"] is True
    assert paused.json()["paused_reason"] == "paused by admin-1: source moving"
    resumed = client.post("/v1/admin/schedules/open/resume")
    assert resumed.status_code == 200 and resumed.json()["paused"] is False
    actions = [(r["action"], r["principal"].id) for r in client.audit.records]
    assert ("pause_schedule", "admin-1") in actions and ("resume_schedule", "admin-1") in actions


def test_a_recipe_with_no_schedule_is_not_found(client: Any) -> None:
    assert client.post("/v1/admin/schedules/nothing/pause", json={}).status_code == 404
    assert client.get("/v1/admin/schedules/nothing/runs").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/admin/schedules"),
        ("get", "/v1/admin/schedules/open/runs"),
        ("post", "/v1/admin/schedules/open/pause"),
        ("post", "/v1/admin/schedules/open/resume"),
        ("post", "/v1/admin/schedules/open/run"),
        ("put", "/v1/admin/schedules/open"),
    ],
)
def test_an_account_without_operate_schedules_is_refused(
    client: Any, method: str, path: str
) -> None:
    app.dependency_overrides[get_principal] = lambda: ANALYST
    body = {"cron": "0 7 * * *"} if method == "put" else {}
    response = getattr(client, method)(path, **({"json": body} if method != "get" else {}))
    assert response.status_code == 403
    assert response.json()["detail"]["right"] == "operate_schedules"
    assert client.recipes.paused == {} and client.executor.ran == []
    assert client.recipes.held[0].schedule_cron == "0 6 * * 1-5"


# --- ADR-110 Amendment 3, point 2: Run now and Change schedule, as the schedule's owner ---------


def test_run_now_runs_as_the_owner_and_names_the_administrator(client: Any) -> None:
    response = client.post("/v1/admin/schedules/open/run")
    assert response.status_code == 200
    assert client.executor.ran == ["open"]
    (record,) = [r for r in client.audit.records if r["action"] == "run_schedule_now"]
    assert record["principal"].id == "admin-1"
    assert record["resolved_query"] == {"recipe_id": "open", "run_as": "approver-1"}


def test_run_now_refused_says_why(client: Any) -> None:
    client.executor.refuse = "the schedule's owner, approver-1, can no longer sign in"
    response = client.post("/v1/admin/schedules/open/run")
    assert response.status_code == 409
    assert response.json() == {
        "error": "run_refused",
        "detail": "the schedule's owner, approver-1, can no longer sign in",
    }


def test_change_schedule_keeps_the_owner_and_is_audited(client: Any) -> None:
    response = client.put(
        "/v1/admin/schedules/open", json={"cron": "30 7 * * 1-5", "timezone": "Europe/London"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schedule"] == "every weekday at 07:30 (Europe/London)"
    assert body["owner"] == "approver-1"
    actions = [(r["action"], r["principal"].id) for r in client.audit.records]
    assert ("change_schedule", "admin-1") in actions


def test_change_schedule_refuses_one_it_could_not_keep(client: Any) -> None:
    response = client.put("/v1/admin/schedules/open", json={"cron": "*/5 * * * *"})
    assert response.status_code == 422
    assert "more often than every 15 minutes" in response.json()["detail"]
    assert client.recipes.held[0].schedule_cron == "0 6 * * 1-5"


def test_change_schedule_re_commits_the_recipe_with_its_new_time(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import services.api.app as app_module

    committed: list[str | None] = []

    async def commit(recipe: StudioRecipeDraft, repo_root: Any) -> None:
        committed.append(recipe.schedule_cron)

    monkeypatch.setattr(app_module, "_commit_schedule", commit)
    client.put("/v1/admin/schedules/open", json={"cron": "30 7 * * 1-5"})
    assert committed == ["30 7 * * 1-5"]


def test_an_admin_schedule_change_on_an_unpinned_row_is_saved_and_re_committed_without_pins(
    client: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-120 Amendment 2, decision 2: the administrator's change of a schedule re-commits the
    recipe with the pins the row holds, which for a row flagged before pinning are none. Red if the
    route refuses it, or invents pins (`{}` or the current versions) that hide a pack bump."""
    import subprocess

    import services.api.app as app_module
    from services.ingest.recipe_loader import load_recipe

    from schemas.ingest import RecipeEntity, RowTemplate

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    built_with: list[object] = []
    real_build = app_module.build_recipe

    def recording_build(*args: Any, **kwargs: Any) -> Any:
        built_with.append(kwargs.get("pack_versions", "not passed"))
        return real_build(*args, **kwargs)

    monkeypatch.setattr(app_module, "build_recipe", recording_build)
    client.recipes.held[0] = client.recipes.held[0].model_copy(
        update={
            "row_template": RowTemplate(
                entities=[RecipeEntity(ref="a", pole_class="object", type="Endpoint")]
            ),
            "connector_profile": "generic-csv",
            "ontology_version": 1,
            "git_path": "recipes/open.yaml",
            "pack_versions": None,
        }
    )

    response = client.put("/v1/admin/schedules/open", json={"cron": "30 7 * * 1-5"})

    assert response.status_code == 200, response.text
    assert client.recipes.held[0].schedule_cron == "30 7 * * 1-5"
    assert built_with == [None]
    committed = tmp_path / "recipes" / "open.yaml"
    assert load_recipe(committed).pack_versions is None
    assert "pack_versions" not in committed.read_text()


def test_an_admin_schedule_change_through_the_route_carries_a_pinned_row_s_pins(
    client: Any, tmp_path: Any
) -> None:
    """ADR-120 Amendment 2, decision 2, through the administrator's route rather than
    `_commit_schedule` alone. The row pins `{"niem": 2}` on a recipe whose own mapping names no
    pack, so recomputing would give `{}`. Red if the route recomputes the pins or drops them."""
    import subprocess

    from services.ingest.recipe_loader import load_recipe

    from schemas.ingest import RecipeEntity, RowTemplate

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    client.recipes.held[0] = client.recipes.held[0].model_copy(
        update={
            "row_template": RowTemplate(
                entities=[RecipeEntity(ref="a", pole_class="object", type="Endpoint")]
            ),
            "connector_profile": "generic-csv",
            "ontology_version": 1,
            "git_path": "recipes/open.yaml",
            "pack_versions": {"niem": 2},
        }
    )

    response = client.put("/v1/admin/schedules/open", json={"cron": "30 7 * * 1-5"})

    assert response.status_code == 200, response.text
    assert load_recipe(tmp_path / "recipes" / "open.yaml").pack_versions == {"niem": 2}


def test_an_admin_schedule_change_on_a_row_with_no_mapping_is_saved(client: Any) -> None:
    """A row with no `row_template` has nothing to re-commit, so it is retimed and nothing is
    written. Red if the route tries to commit a recipe it has no mapping for, which would fail the
    schedule change of a row that holds no mapping."""
    assert client.recipes.held[0].row_template is None
    assert client.recipes.held[0].pack_versions is None

    response = client.put("/v1/admin/schedules/open", json={"cron": "30 7 * * 1-5"})

    assert response.status_code == 200, response.text
    assert client.recipes.held[0].schedule_cron == "30 7 * * 1-5"


def test_a_watched_recipe_is_listed_with_its_watch_in_words(client: Any) -> None:
    """ADR-110 Amendment 4: a recipe run by its folder watch alone is a schedule too."""
    watched = client.recipes.held[0].model_copy(
        update={"recipe_id": "watched", "schedule_cron": None, "schedule_watch": "*.csv",
                "dataset_id": "carrier-b"}
    )  # fmt: skip
    both = client.recipes.held[0].model_copy(
        update={"recipe_id": "both", "schedule_watch": "*.xlsx", "dataset_id": "carrier-b"}
    )
    client.recipes.held += [watched, both]
    listed = {s["recipe_id"]: s for s in client.get("/v1/admin/schedules").json()}
    assert listed["watched"]["schedule"] == (
        "when a file matching `*.csv` arrives in the carrier-b folder"
    )
    assert (listed["watched"]["cron"], listed["watched"]["watch"]) == (None, "*.csv")
    assert listed["watched"]["next_run"] is None
    assert listed["both"]["schedule"] == (
        "every weekday at 06:00 (Europe/London); and when a file matching `*.xlsx` arrives in the "
        "carrier-b folder"
    )


def test_a_watched_runs_file_is_named_only_where_its_source_may_be_viewed(client: Any) -> None:
    """ADR-110 Amendment 4: a file's name in the source's folder is a read, like the counts."""

    class _WatchRuns:
        async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[RecipeRun]:
            run = _run(recipe_id, "SECRET" if recipe_id == "secret" else "OFFICIAL")
            return [run.model_copy(update={"trigger": "watch", "slot": None,
                                           "source_file": "informants-0612.csv|9|1.0"})]  # fmt: skip

    app.dependency_overrides[get_recipe_runs] = _WatchRuns
    (shown,) = client.get("/v1/admin/schedules/open/runs").json()
    (withheld,) = client.get("/v1/admin/schedules/secret/runs").json()
    assert (shown["trigger"], shown["file"]) == ("watch", "informants-0612.csv")
    assert withheld["withheld"] is True and withheld["file"] is None
