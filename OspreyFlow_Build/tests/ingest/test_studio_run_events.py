"""A recipe run from the Ingest Studio stores its events (found building ADR-094 step 2).

`run_published_recipe` dropped the events its run produced (`report, _events = ...`): the only
callers of `AnalyticsPort.load_events` were the seed scripts, so for anything loaded through the
Studio the timeline, *Show messages* and extraction found nothing, however the recipe was written.
What a mistake would do: an SMS export loaded through the Studio, its text marked, would show no
messages. This runs the SMS recipe fixture as a published recipe against its synthetic export."""

from __future__ import annotations

import csv
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.api.studio_publish import run_published_recipe

from demo_fixtures.sms import FIELDS, generate_sms_rows
from ontology.loader import load_default_ontology
from schemas.analytics import EventRecord
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.ingest.test_message_content import LOADER, RecordingGraph

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"


class TransactionalGraph(RecordingGraph):
    async def begin_transaction(self) -> str:
        return "tx-1"

    async def commit_transaction(self, tx: object) -> None:
        return None

    async def rollback_transaction(self, tx: object) -> None:
        return None


class RecordingAnalytics:
    def __init__(self) -> None:
        self.loaded: list[EventRecord] = []

    async def load_events(self, records: list[EventRecord]) -> None:
        self.loaded.extend(records)


async def test_a_studio_run_stores_its_events_with_their_text(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True)
    shutil.copy(FIXTURES / "sms_recipe.yaml", repo / "recipes" / "sms-fixture.yaml")
    source = tmp_path / "carrier-a-sms.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(generate_sms_rows())
    draft = StudioRecipeDraft(
        recipe_id="sms-fixture",
        version=1,
        status=StudioRecipeStatus.PUBLISHED,
        label="SMS",
        connector_profile="generic-csv",
        source_location=str(source),
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        git_path="recipes/sms-fixture.yaml",
    )
    analytics = RecordingAnalytics()
    kwargs: dict[str, Any] = {"analytics": analytics}

    report = await run_published_recipe(
        draft,
        LOADER,
        graph=TransactionalGraph(),  # type: ignore[arg-type]
        ontology=load_default_ontology(),
        load_id="load-1",
        investigation_scope="case-1",
        repo_root=repo,
        **kwargs,
    )

    assert report.rejections == []
    assert len(analytics.loaded) == len(generate_sms_rows())
    assert {e.properties["excerpt"] for e in analytics.loaded} == {r["text"] for r in generate_sms_rows()}
    assert {e.investigation_scope for e in analytics.loaded} == {"case-1"}
