"""Phase 2 exit criterion (`docs/07_BUILD_PLAN.md`): "Load the synthetic CDR
fixture through a hand-written recipe. Every phone-number variant in the
fixture resolves to one `Endpoint`. Duplicate rows collapse to one event
with both source references retained. A timeline histogram over the loaded
events returns correct counts, including across a DST boundary. Rows with
an undeterminable timezone are rejected and counted, never coerced."

Exercises the whole Phase 2 path together: the CSV connector, the
headless recipe engine, the Knowledge Adapters it dispatches to, the
ArcadeDB `GraphPort` adapter (including the edge-merge and weight work),
and the DuckDB `AnalyticsPort` adapter — against a live ArcadeDB, the same
as `tests/conformance/graph_port`.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest
from services.ingest.connectors.csv_connector import read_csv
from services.ingest.engine import StaleRecipeError, run_recipe
from services.ingest.load_ledger import load_record_from_report
from services.ingest.recipe_loader import load_recipe
from services.ingest.revert import LoadAlreadyRevertedError, revert_load

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import EventFilter, HistogramBucketing, HistogramRequest
from schemas.domain import ExpandRequest, Interval, Principal

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


async def test_cdr_fixture_loads_through_a_hand_written_recipe(tmp_path: Path) -> None:
    from tests.scenarios.fixtures.cdr import generate_cdr_rows

    rows = generate_cdr_rows()
    csv_path = tmp_path / "cdr.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["seq", "a_party", "b_party", "start_time", "duration", "direction"]
        )
        writer.writeheader()
        writer.writerows(rows)

    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        report, events = await run_recipe(
            recipe,
            read_csv(csv_path),
            graph=graph,
            ontology=ontology,
            tx=tx,
            principal=CLEARED,
            load_id="load-1",
            investigation_scope="case-cdr-fixture",
            source=str(csv_path),
        )
        await graph.commit_transaction(tx)

        # 10 rows in the fixture; 4 are exact duplicates of an earlier row.
        assert report.rows_read == 10
        assert report.rows_deduplicated == 4
        # Exactly the undeterminable-timestamp row is rejected — never
        # coerced into a guess.
        assert len(report.rejections) == 1
        assert "datetime" in report.rejections[0].reason

        # Every phone-number variant resolves to one Endpoint: one create,
        # four references, for each of the two parties.
        assert report.nodes_created == 2
        assert report.nodes_referenced == 8

        endpoint = await graph.find_node(
            "Endpoint", "value_normalised", "+441621926368", CLEARED
        )
        assert endpoint is not None

        # Duplicate rows collapsed into one summarised edge; every source
        # row reference — including the duplicates' — is retained.
        subgraph = await graph.expand(
            ExpandRequest(node_ids=[endpoint.id], depth=1), CLEARED
        )
        (edge,) = subgraph.edges
        assert edge.occurrences == 5  # 4 unique variant rows + 1 local-time row
        locators = {s.locator for s in edge.provenance.sources}
        assert len(locators) == 5 + 4  # 5 surviving rows' locators + 4 duplicates'

        # A timeline histogram over the loaded events returns correct
        # counts, including across the 2026-03-29 DST boundary the
        # local-time row sits just after.
        async with duckdb_adapter(events, scheme) as analytics:
            window = Interval(
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2026, 4, 1, tzinfo=UTC),
            )
            hist = await analytics.histogram(
                HistogramRequest(
                    filter=EventFilter(investigation_scope="case-cdr-fixture", window=window),
                    bucketing=HistogramBucketing.FIXED_INTERVAL,
                    interval_seconds=86400,
                ),
                CLEARED,
            )
            assert hist.total == 5
            # The DST-adjacent row lands at 2026-03-30 10:00 UTC, not 11:00
            # — proof the histogram is built from the UTC-converted value,
            # not a naive local-time one.
            target_date = datetime(2026, 3, 30, tzinfo=UTC).date()
            dst_bucket = next(
                b for b in hist.buckets if b.start and b.start.date() == target_date
            )
            assert dst_bucket.count == 1

        # Reverting the load — 09_INGEST_STUDIO.md §6: "A load is a unit."
        # No mantis CLI; a plain function, tested directly.
        started_at = datetime.now(UTC)
        record = load_record_from_report(
            report,
            source=str(csv_path),
            created_by=CLEARED.id,
            started_at=started_at,
            now=started_at,
        )
        revert_tx = await graph.begin_transaction()
        reverted_record = await revert_load(
            record, graph=graph, tx=revert_tx, reverted_by="reviewer-1", now=datetime.now(UTC)
        )
        await graph.commit_transaction(revert_tx)

        assert reverted_record.superseded_by == "reviewer-1"
        assert await graph.get_node(endpoint.id, CLEARED) is None
        assert (
            await graph.find_node("Endpoint", "value_normalised", "+441621926368", CLEARED)
            is None
        )

        with pytest.raises(LoadAlreadyRevertedError):
            await revert_load(
                reverted_record,
                graph=graph,
                tx=revert_tx,
                reverted_by="reviewer-2",
                now=datetime.now(UTC),
            )


async def test_a_stale_recipe_is_blocked_not_silently_run(tmp_path: Path) -> None:
    """`09_INGEST_STUDIO.md` §6: "An ontology change that invalidates a
    recipe flags it and blocks scheduled runs until someone opens it.
    Recipes never silently adapt." `default.yaml` moved to v4 when
    `COMMUNICATED_WITH` gained `duration_s`/`direction` — a recipe still
    declaring v3 must be blocked, not run against the new ontology as if
    nothing changed."""
    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    stale_recipe = recipe.model_copy(update={"ontology_version": recipe.ontology_version - 1})
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    csv_path = tmp_path / "cdr.csv"
    csv_path.write_text("seq,a_party,b_party,start_time,duration,direction\n")

    async with arcadedb_adapter(ontology, scheme) as graph:
        tx = await graph.begin_transaction()
        with pytest.raises(StaleRecipeError):
            await run_recipe(
                stale_recipe,
                read_csv(csv_path),
                graph=graph,
                ontology=ontology,
                tx=tx,
                principal=CLEARED,
                load_id="load-stale",
                investigation_scope="case-cdr-fixture",
                source=str(csv_path),
            )
        await graph.rollback_transaction(tx)
