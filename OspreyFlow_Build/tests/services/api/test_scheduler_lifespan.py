"""ADR-110's cost section: "a fake clock proves the arithmetic but not the lifespan". This starts a
real Conduit process on the throwaway stores, puts a due schedule in its recipe store, and waits for
the Conduit's own minute tick to judge it and write the ledger.

The test stack has no identity provider to act as the schedule's owner through, so the honest outcome
is a refusal in words — which is what a deployment whose identity provider is down records too. What
is proved is the path: the lifespan task, the claim, the owner check and the ledger, live.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_recipes import StudioRecipeStore

from conduit_common.identity import new_id
from ontology.loader import load_default_ontology
from tests.services.api.test_statelessness import _ConduitInstance

HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "owning_unit": "unit-1",
    "originator": "unit-1",
}


async def _schedule_a_due_recipe() -> str:
    recipe_id = new_id()
    store = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)  # makes the columns
    await store.close()
    import asyncpg

    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        now = datetime.now(UTC)
        # (ADR-120 Amendment 1: a pinned row, so start-up's reconcile leaves it published)
        await conn.execute(
            "INSERT INTO studio_recipes (recipe_id, version, ontology_version, label, status, "
            "content, git_path, owning_unit, created_by, published_by, schedule_cron, created_at, "
            "published_at, schedule_owner, schedule_set_at, schedule_case, schedule_timezone, "
            "pack_versions) "
            "VALUES ($1, 1, $5, 'Lifespan check', 'published', $2, 'recipes/x.yaml', 'unit-1', "
            "'author-1', 'approver-1', '*/15 * * * *', $3, $3, 'approver-1', $4, 'case-1', "
            "'Europe/London', '{}')",
            recipe_id,
            json.dumps({"handling": HANDLING}),
            now,
            now - timedelta(minutes=20),  # so at least one 15-minute slot is already due
            # The ontology the Conduit serves: an older one is flagged at its start, and blocked.
            load_default_ontology().version,
        )
    finally:
        await conn.close()
    return recipe_id


async def _ledger(recipe_id: str) -> list[tuple[str, str | None]]:
    runs = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        return [(r.outcome, r.failure) for r in await runs.for_recipe(recipe_id)]
    finally:
        await runs.close()


def test_the_conduits_own_tick_judges_a_due_schedule_and_writes_the_ledger(jwks_url: str) -> None:
    recipe_id = asyncio.run(_schedule_a_due_recipe())
    conduit = _ConduitInstance(jwks_url)
    try:
        deadline = time.monotonic() + 90  # the tick is at the top of each minute
        rows: list[tuple[str, str | None]] = []
        while time.monotonic() < deadline and not rows:
            time.sleep(2)
            rows = asyncio.run(_ledger(recipe_id))
    finally:
        conduit.kill()
    assert rows, "no tick judged the due schedule within 90 seconds"
    (outcome, failure), *_ = rows
    assert outcome == "refused"
    assert failure and "owner" in failure
