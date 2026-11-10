"""External orchestration's run API against the real run ledger in Postgres and a real Valkey
(`06_DECISIONS.md` ADR-141 decisions 6, 10, 12 and its named tests).

- An external trigger whose pipeline's owner has lost the studio role, the Editor level or the
  clearance is refused in words and recorded *refused*; the run acts as the owner, never as the
  service identity (red if `start_external_run` ran as the identity: the ledger's `run_as` and the
  principal the run is given are both checked).
- The same external run id twice loads once (red with the key ignored: the ledger's partial unique
  index is what holds it, so this must be the real ledger); a refused trigger's retry is judged
  again.
- A dataset's quota of one run a day refuses the second run in words and records it (the
  redesign's phase 10 exit), through `begin_run`, the start every trigger's run passes.
- What the identity reads back is withheld where the owner may not view a marking the run wrote.

The owner's edges are `test_schedule_executor.py`'s, each refusing what the real one refuses; the
load itself is a stand-in that finishes the ledger row, as `continue_run` does. Every row and lock
a test writes is removed in teardown, even when it fails.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest
from services.api import external_runs
from services.api.config import PostgresConfig
from services.api.external_runs import start_external_run, status_for
from services.api.recipe_runs import External, RecipeRunStore
from services.api.run_quotas import InMemoryQuotaStore
from valkey.asyncio import Valkey

from conduit_common.identity import new_id
from principal_auth import PrincipalRevoked
from schemas.domain import Handling, Principal
from schemas.ingest import LoadReport, StudioRecipeDraft
from schemas.operations import RunQuota
from tests.services.api.test_schedule_executor import (  # noqa: F401  (fixtures)
    OWNER,
    SCHEME,
    _Edges,
    _executor,
    _recipe,
    _Recipes,
    runs,
    valkey,
)

# ruff: noqa: F811  (the imported fixtures are each test's own same-named parameters)

LOADER_OWNER = OWNER.model_copy(update={"roles": ["source_approver", "loader"]})
CLIENT = "airflow-prod"


@pytest.fixture
async def written(runs: RecipeRunStore, valkey: Valkey) -> AsyncIterator[list[str]]:
    """The recipe ids a test writes runs for; their rows and locks are removed afterwards."""
    ids: list[str] = []
    yield ids
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        await conn.execute("DELETE FROM recipe_runs WHERE recipe_id = ANY($1::text[])", ids)
    finally:
        await conn.close()
    for recipe_id in ids:
        await valkey.delete(f"schedule:lock:{recipe_id}")


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> list[Principal]:
    """The load, as `continue_run` ends it: the ledger row finished. Records who it ran as."""
    principals: list[Principal] = []

    async def fake_continue(
        deps: Any, *, run_id: str, principal: Principal, recipe: StudioRecipeDraft, **_: Any
    ) -> LoadReport:
        principals.append(principal)
        report = LoadReport(
            load_id=new_id(), recipe_id=recipe.recipe_id, recipe_version=recipe.version,
            rows_read=5, rows_held=1,
        )  # fmt: skip
        await deps.recipe_runs.finish(run_id, report=report, now=datetime.now(UTC))
        return report

    monkeypatch.setattr(external_runs, "continue_run", fake_continue)
    return principals


def _external_recipe() -> StudioRecipeDraft:
    return _recipe(
        schedule_cron=None, schedule_owner=LOADER_OWNER.id, schedule_case="case-1",
        owned_externally_by=CLIENT, dataset_id="ds-1",
    )  # fmt: skip


async def _start(
    runs: RecipeRunStore,
    valkey: Valkey,
    edges: _Edges,
    recipe: StudioRecipeDraft,
    external_id: str,
    *,
    quotas: InMemoryQuotaStore | None = None,
    spawned: list[Any] | None = None,
) -> Any:
    tasks = spawned if spawned is not None else []

    async def resolve(owner_id: str) -> Principal | None:
        return edges.owner if isinstance(edges.owner, Principal) else None

    status = await start_external_run(
        deps=SimpleNamespace(recipe_runs=runs, run_quotas=quotas, handling_scheme=SCHEME),  # type: ignore[arg-type]
        executor=_executor(_Recipes([recipe]), edges, runs, valkey),
        valkey=valkey,
        recipe=recipe,
        external=External(run_id=external_id, triggered_by=CLIENT),
        spawn=lambda work: tasks.append(work),
        resolve_owner=resolve,
    )
    for work in tasks:
        await work
    tasks.clear()
    return status


async def test_an_external_run_acts_as_the_owner_and_is_recorded_as_external(
    runs: RecipeRunStore, valkey: Valkey, written: list[str], loaded: list[Principal]
) -> None:
    recipe = _external_recipe()
    written.append(recipe.recipe_id)
    status = await _start(runs, valkey, _Edges(owner=LOADER_OWNER), recipe, "dag:run-1")
    assert status.outcome == "running"
    assert [p.id for p in loaded] == [LOADER_OWNER.id]
    run = await runs.get(status.run_id)
    assert run is not None
    assert (run.trigger, run.run_as, run.triggered_by, run.external_run_id) == (
        "external", LOADER_OWNER.id, CLIENT, "dag:run-1",
    )  # fmt: skip
    assert run.outcome == "succeeded" and run.dataset_id == "ds-1" and run.owning_unit == "unit-1"


@pytest.mark.parametrize(
    ("edges", "words"),
    [
        (_Edges(owner=OWNER), "no longer holds the loader's studio role"),
        (_Edges(owner=LOADER_OWNER, case_level_ok=False), "is no longer an Editor of its case"),
        (
            _Edges(owner=LOADER_OWNER.model_copy(update={"clearance": "UNCLASSIFIED"})),
            "the source is marked above the clearance",
        ),
        (_Edges(owner=PrincipalRevoked("gone")), "can no longer sign in"),
    ],
    ids=["studio-role", "editor-level", "clearance", "revoked"],
)
async def test_an_owner_who_may_no_longer_run_it_is_refused_in_words_and_recorded(
    runs: RecipeRunStore,
    valkey: Valkey,
    written: list[str],
    loaded: list[Principal],
    edges: _Edges,
    words: str,
) -> None:
    recipe = _external_recipe()
    written.append(recipe.recipe_id)
    status = await _start(runs, valkey, edges, recipe, "dag:refused-1")
    assert status.outcome == "refused" and words in (status.words or "")
    assert LOADER_OWNER.id not in (status.words or ""), "no account id reaches the identity"
    assert loaded == []
    run = await runs.get(status.run_id)
    assert run is not None
    assert (run.outcome, run.trigger, run.run_as, run.triggered_by) == (
        "refused", "external", LOADER_OWNER.id, CLIENT,
    )  # fmt: skip


async def test_the_same_external_run_id_twice_loads_once(
    runs: RecipeRunStore, valkey: Valkey, written: list[str], loaded: list[Principal]
) -> None:
    recipe = _external_recipe()
    written.append(recipe.recipe_id)
    edges = _Edges(owner=LOADER_OWNER)
    first = await _start(runs, valkey, edges, recipe, "dag:retried")
    second = await _start(runs, valkey, edges, recipe, "dag:retried")
    assert len(loaded) == 1
    assert second.already_recorded and second.run_id == first.run_id
    assert len(await runs.for_recipe(recipe.recipe_id)) == 1


async def test_two_starts_racing_with_one_id_load_once(
    runs: RecipeRunStore, valkey: Valkey, written: list[str], loaded: list[Principal]
) -> None:
    """The ledger's unique index, not the look-up before it, holds the key: the look-up is passed
    over by starting the second with the first's row not yet visible to it."""
    recipe = _external_recipe()
    written.append(recipe.recipe_id)
    await runs.start(
        recipe_id=recipe.recipe_id, recipe_version=recipe.version, investigation_id="case-1",
        trigger="external", slot=None, run_as=LOADER_OWNER.id,
        source=Handling.model_validate(recipe.handling), now=datetime.now(UTC),
        external=External(run_id="dag:raced", triggered_by=CLIENT),
    )  # fmt: skip
    from services.api.recipe_runs import ExternalRunRecorded

    with pytest.raises(ExternalRunRecorded):
        await runs.start(
            recipe_id=recipe.recipe_id, recipe_version=recipe.version, investigation_id="case-1",
            trigger="external", slot=None, run_as=LOADER_OWNER.id,
            source=Handling.model_validate(recipe.handling), now=datetime.now(UTC),
            external=External(run_id="dag:raced", triggered_by=CLIENT),
        )  # fmt: skip
    assert len(await runs.for_recipe(recipe.recipe_id)) == 1


async def test_a_refused_triggers_retry_is_judged_again(
    runs: RecipeRunStore, valkey: Valkey, written: list[str], loaded: list[Principal]
) -> None:
    recipe = _external_recipe()
    written.append(recipe.recipe_id)
    refused = await _start(runs, valkey, _Edges(owner=OWNER), recipe, "dag:again")
    assert refused.outcome == "refused"
    ran = await _start(runs, valkey, _Edges(owner=LOADER_OWNER), recipe, "dag:again")
    assert ran.outcome == "running" and not ran.already_recorded and len(loaded) == 1


async def test_a_quota_of_one_run_a_day_refuses_the_second_in_words(
    runs: RecipeRunStore, valkey: Valkey, written: list[str], loaded: list[Principal]
) -> None:
    recipe = _external_recipe().model_copy(update={"dataset_id": f"ds-{new_id()}"})
    written.append(recipe.recipe_id)
    quotas = InMemoryQuotaStore()
    await quotas.set(RunQuota(scope="dataset", key=recipe.dataset_id or "", runs_per_day=1))
    edges = _Edges(owner=LOADER_OWNER)
    first = await _start(runs, valkey, edges, recipe, "dag:day-1", quotas=quotas)
    second = await _start(runs, valkey, edges, recipe, "dag:day-2", quotas=quotas)
    assert first.outcome == "running" and len(loaded) == 1
    assert second.outcome == "refused"
    assert "the dataset's quota of 1 run a day is used;" in (second.words or "")
    recorded = await runs.get(second.run_id)
    assert recorded is not None and recorded.outcome == "refused"
    assert quotas.raised, "the budget alert is raised at the quota's share"


async def test_what_the_identity_reads_back_is_withheld_above_the_owner(
    runs: RecipeRunStore, valkey: Valkey, written: list[str], loaded: list[Principal]
) -> None:
    recipe = _external_recipe()
    written.append(recipe.recipe_id)
    status = await _start(runs, valkey, _Edges(owner=LOADER_OWNER), recipe, "dag:read")
    run = await runs.get(status.run_id)
    assert run is not None
    seen = await status_for(run, owner=LOADER_OWNER, scheme=SCHEME)
    assert (seen.rows_read, seen.rows_held, seen.withheld) == (5, 1, False)
    secret = run.model_copy(
        update={
            "markings": [Handling.model_validate({**recipe.handling, "classification": "SECRET"})]
        }
    )
    hidden = await status_for(secret, owner=LOADER_OWNER, scheme=SCHEME)
    assert (hidden.rows_read, hidden.rows_held, hidden.withheld) == (None, None, True)
    unresolved = await status_for(run, owner=None, scheme=SCHEME)
    assert unresolved.withheld and unresolved.rows_read is None


async def test_two_starts_racing_for_a_quotas_last_run_take_it_once(
    runs: RecipeRunStore, written: list[str]
) -> None:
    """The lane review of L1.7, item 11: the count and the row are one step under the quota's
    lock, so two pipelines of one dataset cannot both take its last run."""
    import asyncio

    from services.api.recipe_runs import Counted
    from services.api.run_quotas import QuotaLimit, QuotaRefused, day_start

    dataset = f"ds-race-{new_id()}"
    ids = [f"rcp-race-{new_id()}", f"rcp-race-{new_id()}"]
    written.extend(ids)
    now = datetime.now(UTC)
    limit = QuotaLimit("dataset", dataset, 1, day_start(now))

    async def start(recipe_id: str) -> str:
        return await runs.start(
            recipe_id=recipe_id, recipe_version=1, investigation_id="case-1", trigger="manual",
            slot=None, run_as=LOADER_OWNER.id, source=Handling.model_validate(_recipe().handling),
            now=now, counted=Counted(dataset, "unit-1"), within=[limit],
        )  # fmt: skip

    outcomes = await asyncio.gather(*(start(r) for r in ids), return_exceptions=True)
    assert sum(isinstance(o, str) for o in outcomes) == 1
    assert sum(isinstance(o, QuotaRefused) for o in outcomes) == 1


async def test_the_postgres_quota_store_keeps_quotas_and_raises_an_alert_once() -> None:
    from services.api.run_quotas import PostgresQuotaStore, QuotaAlert

    store = await PostgresQuotaStore.connect(PostgresConfig.from_env().dsn)
    key = f"ds-q-{new_id()}"
    try:
        await store.set(RunQuota(scope="dataset", key=key, runs_per_day=3, alert_at_share=0.5))
        assert (await store.get("dataset", key)) == RunQuota(
            scope="dataset", key=key, runs_per_day=3, alert_at_share=0.5
        )
        assert [q.key for q in await store.reached_by(units=["unit-x"], datasets=[key])] == [key]
        assert await store.reached_by(units=["unit-x"], datasets=["another"]) == []
        alert = QuotaAlert("dataset", key, "2026-11-10", "reached")
        assert await store.raise_once(alert, at=datetime.now(UTC)) is True
        assert await store.raise_once(alert, at=datetime.now(UTC)) is False
        assert [
            a.key for a in await store.alerts(since_day="2026-11-01", of=[("dataset", key)])
        ] == [key]
        assert await store.alerts(since_day="2026-11-01", of=[("dataset", "another")]) == []
    finally:
        conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
        try:
            await conn.execute("DELETE FROM run_quotas WHERE key = $1", key)
            await conn.execute("DELETE FROM quota_alerts WHERE key = $1", key)
        finally:
            await conn.close()
        await store.close()
