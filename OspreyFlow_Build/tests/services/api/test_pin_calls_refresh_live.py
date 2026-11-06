"""Redesign phase 4's exit (`BUILD_PLAN_INGEST_STUDIO.md`): the demo's PIN-call file, read again by
its source's refresh, creates nothing new and holds each event once, as a full snapshot with
*withdraw* and as an incremental refresh on its `call_start`.

Live, through the path a source refresh takes (`run_published_recipe` with the source's
`RefreshRead`, a `LedgerSink` over the real run ledger): ArcadeDB on `ARCADEDB_HTTP_PORT`, Postgres
on `POSTGRES_PORT`, DuckDB in memory. The file is the Prison Intelligence Dataset's own (synthetic,
`demo_fixtures.pid_files`), the committed `pid-pin-calls` recipe reading it. It loads after the
establishment plan and the prisoners, as the seed does, since a call's prisoner is found by
reference. The rows are R5's slice (`pin_calls_slice`: every link holding a planted duplicate, the
coordinator's number, and numbers written in other forms), which keeps a live case to a few
minutes; R5 holds the engine to the same over the slice, and the whole file is the coordinator's on
a quiet stack.

What a mistake would do, and the case that catches it:

- a re-read creating a node or a link, or writing an event again (the timeline doubled), or taking
  a row it carries for dropped and withdrawing it
  (`test_the_pin_call_file_read_again_creates_nothing_and_holds_each_event_once`);
- an incremental re-read reading the file again past its own watermark (the same case)."""

from __future__ import annotations

import csv
from pathlib import Path

from services.api.load_records import LedgerSink
from services.api.recipe_runs import RecipeRunStore
from services.api.studio_publish import load_with_rules, run_published_recipe, serialise_recipe
from services.ingest.watermark import RefreshRead

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.analytics import EventFilter, EventListRequest
from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus
from tests.ingest.pid_golden_support import (
    CALLS,
    LOADER,
    ONTOLOGY,
    SCHEME,
    pin_calls_slice,
    recipe_for,
    rows_of,
)
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.services.api.test_source_refresh_snapshot_live import NOW, SOURCE, runs

__all__ = ["runs"]  # the fixture, used by name

BEFORE = ("pid_establishment_plan.csv", "pid_nomis_prisoners.csv")
SNAPSHOT = RefreshRead(source_id="src-pin-calls", mode="snapshot", dropped_rows="withdraw")
INCREMENTAL = RefreshRead(
    source_id="src-pin-calls", mode="incremental", watermark_column="call_start"
)


def _published(tmp_path: Path) -> tuple[Path, StudioRecipeDraft]:
    recipe = recipe_for(CALLS)
    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True)
    (repo / "recipes" / f"{recipe.id}.yaml").write_text(serialise_recipe(recipe))
    rows = list(pin_calls_slice()[0])
    file = tmp_path / CALLS
    with file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_of(CALLS)[0]))
        writer.writeheader()
        writer.writerows(rows)
    draft = StudioRecipeDraft(
        recipe_id=recipe.id, version=recipe.version, status=StudioRecipeStatus.PUBLISHED,
        label=recipe.label, connector_profile=recipe.connector.profile, source_location=str(file),
        owning_unit="fenwick-moor-security", created_by="data-engineer-1", created_at=NOW,
        git_path=f"recipes/{recipe.id}.yaml",
    )  # fmt: skip
    return repo, draft


async def test_the_pin_call_file_read_again_creates_nothing_and_holds_each_event_once(
    tmp_path: Path, runs: RecipeRunStore
) -> None:
    case = new_id()
    repo, draft = _published(tmp_path)
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph, duckdb_adapter([], SCHEME) as analytics:
        for file in BEFORE:
            report, _, _ = await load_with_rules(
                recipe_for(file), list(rows_of(file)), LOADER, graph=graph, ontology=ONTOLOGY,
                load_id=new_id(), investigation_scope=case, source=file,
                media=InMemoryMediaStore(), rules=None, scheme=SCHEME, sink=None,
            )  # fmt: skip
            assert report.rejections == [], (file, report.rejections[:3])

        async def refresh(read: RefreshRead, minute: int) -> object:
            from datetime import timedelta

            started = NOW + timedelta(minutes=minute)
            run_id = await runs.start(
                recipe_id=draft.recipe_id, recipe_version=draft.version, investigation_id=case,
                trigger="source_refresh", slot=None, run_as=LOADER.id, source=SOURCE, now=started,
            )  # fmt: skip
            sink = LedgerSink(
                runs, run_id, created_by=LOADER.id, investigation_id=case, started_at=started
            )
            report = await run_published_recipe(
                draft, LOADER, graph=graph, ontology=ONTOLOGY, load_id=new_id(),  # type: ignore[arg-type]
                investigation_scope=case, repo_root=repo, analytics=analytics,  # type: ignore[arg-type]
                media=InMemoryMediaStore(), scheme=SCHEME, sink=sink, refresh=read,
            )  # fmt: skip
            await runs.finish(run_id, report=report, now=started)
            return report

        async def events() -> int:
            page = await analytics.list_events(  # type: ignore[attr-defined]
                EventListRequest(filter=EventFilter(investigation_scope=case), limit=1), LOADER
            )
            return int(page.total)

        rows = len(pin_calls_slice()[0])
        first = await refresh(SNAPSHOT, 1)
        assert first.rejections == [] and first.nodes_created > 0  # type: ignore[attr-defined]
        held = await events()
        assert held == first.rows_read - first.rows_deduplicated  # type: ignore[attr-defined]

        again = await refresh(SNAPSHOT, 2)
        assert again.rows_already_loaded == rows, "every row's key is kept"  # type: ignore[attr-defined]
        assert (again.nodes_created, again.edges_created, again.rows_withdrawn) == (0, 0, 0)  # type: ignore[attr-defined]
        assert again.withdrawn_node_ids == [] and again.withdrawn_edge_ids == []  # type: ignore[attr-defined]
        assert await events() == held, "each event held once"

        # The first incremental read has no watermark of its own yet: it reads the file, keeps
        # every row as loaded, and reaches the latest call. The next reads nothing past it.
        primed = await refresh(INCREMENTAL, 3)
        assert (primed.nodes_created, primed.edges_created) == (0, 0)  # type: ignore[attr-defined]
        past = await refresh(INCREMENTAL, 4)
        assert past.rows_read == 0 and past.rows_below_watermark == rows  # type: ignore[attr-defined]
        assert (past.nodes_created, past.edges_created) == (0, 0)  # type: ignore[attr-defined]
        assert await events() == held, "each event held once"
