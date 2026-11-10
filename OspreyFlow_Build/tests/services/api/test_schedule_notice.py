"""ADR-110 decision 10 and Amendment 3, point 1: a failed or refused scheduled run tells its owner,
as an alert with no typology in the owner's own inbox — with its words on the personal alert view —
and never in the case team's queue. Against the throwaway Postgres; the view through its own
function."""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.scheduler import schedule_notice
from services.api.alert_queue import monitoring_queue

from conduit_common.identity import new_id
from schemas.domain import Principal
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

from tests.services.api.no_transactions import NO_TRANSACTIONS

NOW = datetime(2026, 6, 2, 5, tzinfo=UTC)


def _recipe(case: str) -> StudioRecipeDraft:
    return StudioRecipeDraft(  # type: ignore[call-arg]
        recipe_id=new_id(), version=1, status=StudioRecipeStatus.PUBLISHED, label="Daily export",
        handling={}, owning_unit="unit-1", created_by="a", created_at=NOW, ready_for_profile=True,
        schedule_cron="0 6 * * *", schedule_owner="approver-1", schedule_case=case,
    )  # fmt: skip


async def test_a_notice_reaches_the_owners_inbox_with_its_words_and_no_case_queue() -> None:
    case, owner = new_id(), f"owner-{new_id()}"
    recipe = _recipe(case)
    notice = schedule_notice(owner, recipe, "The scheduled run of Daily export was refused: x", NOW)
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.save(notice)
        reader = Principal(id=owner, clearance="OFFICIAL", org_unit="unit-1")
        (mine,) = await store.list_authorized(reader)
        assert mine.id == notice.id and mine.typology is None
        assert await store.list_case_queue(case, reader) == []
        # L2.10 (ADR-146 decision 1): the inbox went into the one queue, which shows the notice to
        # its owner, with its words and no referent, and to no one else in the case.
        (queued,) = await monitoring_queue(store, None, NO_TRANSACTIONS, case, reader)  # type: ignore[arg-type]
        assert queued.alert.id == notice.id
        assert queued.alert.words == "The scheduled run of Daily export was refused: x"
        assert queued.alert.rule_id == f"schedule:{recipe.recipe_id}" and queued.alert.referent_node_ids == []
        someone_else = reader.model_copy(update={"id": f"other-{new_id()}"})
        assert await store.list_authorized(someone_else) == []
        assert await monitoring_queue(store, None, NO_TRANSACTIONS, case, someone_else) == []  # type: ignore[arg-type]
    finally:
        await store.close()
