"""Phase 2 exit criterion: "Load the synthetic CDR
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
from services.ingest.engine import StaleRecipeError, preview_handling_and_provenance, run_recipe
from services.ingest.load_ledger import load_record_from_report
from services.ingest.load_revert import RevertDeps, RevertRefused, revert
from services.ingest.recipe_loader import load_recipe

from adapters.analytics_duckdb.testing import duckdb_adapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.analytics import EventFilter, HistogramBucketing, HistogramRequest
from schemas.domain import ExpandRequest, Interval, Principal
from tests.ingest.test_revert_load import Alerts, Audit, Held, Ledger, Steps

FIXTURES = Path(__file__).resolve().parents[1] / "scenarios" / "fixtures"

CLEARED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


async def test_cdr_fixture_loads_through_a_hand_written_recipe(tmp_path: Path) -> None:
    from demo_fixtures.cdr import generate_cdr_rows

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

        # Reverting the load — 09_INGEST_STUDIO.md §6: "A load is a unit." The revert reads the
        # load's record (the ids it created, never the `load_id` stored on an element) and refuses a
        # load that merged (ADR-127 Amendment 6); the ledger and the audit trail are stand-ins here.
        started_at = datetime.now(UTC)
        record = load_record_from_report(
            report,
            source=str(csv_path),
            created_by=CLEARED.id,
            started_at=started_at,
            now=started_at,
        )
        assert record.merged_edge_ids == [] and record.merged_node_ids == []
        steps = Steps()
        async with duckdb_adapter(events, scheme) as analytics:
            assert all(e.load_id == "load-1" for e in events)
            deps = RevertDeps(
                ledger=Ledger(record),
                graph=graph,
                analytics=analytics,
                held_rows=Held(steps),
                alerts=Alerts(steps),
                audit=Audit(steps),
            )
            result = await revert(
                "load-1", reverted_by="reviewer-1", deps=deps, now=datetime.now(UTC)
            )
            (reverted,) = result.reverted
            assert (reverted.nodes, reverted.events) == (2, len(events))
            window = Interval(
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2026, 4, 1, tzinfo=UTC),
            )
            gone = await analytics.histogram(
                HistogramRequest(
                    filter=EventFilter(investigation_scope="case-cdr-fixture", window=window),
                    bucketing=HistogramBucketing.FIXED_INTERVAL,
                    interval_seconds=86400,
                ),
                CLEARED,
            )
            assert gone.total == 0, "the load's events left the timeline with it"

        assert deps.ledger.records["load-1"].reverted_by == "reviewer-1"  # type: ignore[attr-defined]
        assert await graph.get_node(endpoint.id, CLEARED) is None
        assert (
            await graph.find_node("Endpoint", "value_normalised", "+441621926368", CLEARED)
            is None
        )

        # A second revert is refused, and changes nothing more.
        with pytest.raises(RevertRefused) as refused:
            await revert("load-1", reverted_by="reviewer-2", deps=deps, now=datetime.now(UTC))
        assert [r.reason for r in refused.value.refusals] == ["already_reverted"]


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


def test_preview_handling_and_provenance_needs_no_transaction() -> None:
    """`09_INGEST_STUDIO.md` §4/§5: Map's live preview and Verify's dry run
    call this to show what an element's handling/provenance would be
    before any write — it must work with nothing but the recipe itself,
    no `GraphPort`, no `_RunState`."""
    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    now = datetime(2026, 3, 11, 19, 42, 1, tzinfo=UTC)

    handling, provenance = preview_handling_and_provenance(
        recipe, source="cdr.csv", row_index=0, now=now
    )

    assert handling.classification == "OFFICIAL"
    assert handling.handling_code == "P"
    assert handling.owning_unit == "unit-1"
    assert provenance.state.value == "asserted"
    assert provenance.sources[0].document_id == "cdr.csv"
    assert provenance.sources[0].locator == "row 0"
    assert provenance.first_seen == now


# --- Pack pins (ADR-120 D10, Amendment 1) -------------------------------------
#
# What each test checks, and the violation that fails it:
# - `test_a_stale_pack_pin_is_refused`: a run proceeding against a pack whose version moved.
# - `test_a_pinned_pack_the_ontology_lacks_is_refused`: a pin on a pack the loaded ontology does not
#   carry being treated as unchanged (a `KeyError`, or a silent pass).
# - `test_a_recipe_naming_a_pack_with_no_pin_is_refused`: an unpinned recipe naming a pack running
#   (the legacy-recipe hole the pin exists to close).
# - `test_a_recipe_pinning_the_loaded_version_runs`: the check refusing a recipe it should accept.
# - `test_a_recipe_naming_no_pack_still_runs_unpinned`: the check demanding a pin of a recipe that
#   names and writes no pack, which would break every existing recipe.
# - `test_a_recipe_writing_fibo_types_under_the_core_is_refused_when_it_pins_nothing_for_fibo`: a
#   recipe that writes a pack's types without naming the pack escaping the check, or an empty map
#   or another pack's pin standing in for the pin that is missing.
# - `test_a_recipe_writing_fibo_types_under_the_core_runs_when_pinned`: the check refusing a
#   recipe whose written pack is pinned at the loaded version.
# - `test_a_recipe_naming_no_pack_and_pinning_an_empty_map_runs_on_the_deployment_ontology`: an
#   empty map being read as a pin that differs, for a recipe with nothing to pin.
# - `test_an_extra_pin_is_ignored`: a pin on a pack the recipe neither names nor writes being
#   checked, so a recipe is refused for a pack it does not use.
# - `test_an_extra_pin_on_a_pack_the_ontology_lacks_is_ignored`: the same, for a pin that names a
#   pack the ontology does not even carry (a `KeyError` on the lookup, or a refusal).
# - `test_a_dry_run_of_an_unpinned_draft_writing_fibo_is_not_refused`: the pin check reaching
#   Verify's dry run, which would make a draft impossible to verify before it can be published
#   (a draft is not yet pinned).

_COLUMNS = ["seq", "a_party", "b_party", "start_time", "duration", "direction"]
_EMPTY_CDR = ",".join(_COLUMNS) + "\n"
_ACCOUNT_TEMPLATE = {
    "entities": [
        {
            "ref": "a",
            "pole_class": "object",
            "type": "Account",
            "match_on": "account_number",
            "on_match": "reference",
            "properties": {"account_number": {"field": "iban"}},
        }
    ]
}


def _recipe_from_yaml(
    tmp_path: Path,
    *,
    ontology_version: int,
    pack_versions: dict[str, int] | None,
    domain_pack: str | None = None,
    row_template: dict[str, object] | None = None,
):  # type: ignore[no-untyped-def]
    """A recipe written to YAML and read back through `load_recipe`, as a published one is."""
    import yaml

    document = yaml.safe_load((FIXTURES / "cdr_recipe.yaml").read_text())
    document["ontology_version"] = ontology_version
    if row_template is not None:
        document["row_template"] = row_template
        document.pop("deduplicate", None)
        document.pop("unmapped_fields", None)
    if domain_pack is not None:
        document["pipeline"] = {
            "nodes": [
                {
                    "id": "domain",
                    "kind": "domain_model",
                    "label": "D",
                    "config": {"pack": domain_pack},
                }
            ],
            "edges": [],
        }
    if pack_versions is not None:
        document["pack_versions"] = pack_versions
    path = tmp_path / f"recipe-{len(list(tmp_path.glob('recipe-*.yaml')))}.yaml"
    path.write_text(yaml.safe_dump(document))
    return load_recipe(path)


async def _run_against(recipe, ontology, csv_path: Path):  # type: ignore[no-untyped-def]
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        tx = await graph.begin_transaction()
        try:
            report, _events = await run_recipe(
                recipe,
                read_csv(csv_path),
                graph=graph,
                ontology=ontology,
                tx=tx,
                principal=CLEARED,
                load_id="load-pack-pin",
                investigation_scope="case-cdr-fixture",
                source=str(csv_path),
            )
        except BaseException:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
        return report


def _empty_cdr_csv(tmp_path: Path) -> Path:
    path = tmp_path / "empty.csv"
    path.write_text(_EMPTY_CDR)
    return path


def _cdr_csv(tmp_path: Path) -> Path:
    from demo_fixtures.cdr import generate_cdr_rows

    path = tmp_path / "cdr.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(generate_cdr_rows())
    return path


def _account_csv(tmp_path: Path) -> Path:
    path = tmp_path / "accounts.csv"
    path.write_text("iban\nGB00SYNTH00000001\n")
    return path


async def test_a_stale_pack_pin_is_refused(tmp_path: Path) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path, ontology_version=ontology.version, pack_versions={"niem": 2}, domain_pack="niem"
    )
    with pytest.raises(StaleRecipeError, match="niem"):
        await _run_against(recipe, ontology, _empty_cdr_csv(tmp_path))


async def test_a_pinned_pack_the_ontology_lacks_is_refused(tmp_path: Path) -> None:
    ontology = load_default_ontology()
    recipe = _recipe_from_yaml(
        tmp_path, ontology_version=ontology.version, pack_versions={"niem": 3}, domain_pack="niem"
    )
    with pytest.raises(StaleRecipeError, match="niem"):
        await _run_against(recipe, ontology, _empty_cdr_csv(tmp_path))


async def test_a_recipe_naming_a_pack_with_no_pin_is_refused(tmp_path: Path) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path, ontology_version=ontology.version, pack_versions=None, domain_pack="niem"
    )
    with pytest.raises(StaleRecipeError, match="not pinned"):
        await _run_against(recipe, ontology, _empty_cdr_csv(tmp_path))


async def test_a_recipe_pinning_the_loaded_version_runs(tmp_path: Path) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path,
        ontology_version=ontology.version,
        pack_versions={"niem": ontology.packs["niem"]},
        domain_pack="niem",
    )
    report = await _run_against(recipe, ontology, _cdr_csv(tmp_path))
    assert report.rows_read == 10
    assert report.nodes_created == 2


async def test_a_recipe_naming_no_pack_still_runs_unpinned(tmp_path: Path) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    assert recipe.pipeline is None
    report = await _run_against(recipe, ontology, _cdr_csv(tmp_path))
    assert report.rows_read == 10


@pytest.mark.parametrize("pins", [{}, {"niem": 3}], ids=["empty-map", "another-pack-only"])
async def test_a_recipe_writing_fibo_types_under_the_core_is_refused_when_it_pins_nothing_for_fibo(
    tmp_path: Path, pins: dict[str, int]
) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path,
        ontology_version=ontology.version,
        pack_versions=pins,
        domain_pack="pole",
        row_template=_ACCOUNT_TEMPLATE,
    )
    with pytest.raises(StaleRecipeError, match="fibo"):
        await _run_against(recipe, ontology, _account_csv(tmp_path))


async def test_a_recipe_writing_fibo_types_under_the_core_runs_when_pinned(
    tmp_path: Path,
) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path,
        ontology_version=ontology.version,
        pack_versions={"fibo": ontology.packs["fibo"]},
        domain_pack="pole",
        row_template=_ACCOUNT_TEMPLATE,
    )
    report = await _run_against(recipe, ontology, _account_csv(tmp_path))
    assert report.rows_read == 1
    assert report.nodes_created == 1


async def test_a_recipe_naming_no_pack_and_pinning_an_empty_map_runs_on_the_deployment_ontology(
    tmp_path: Path,
) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(tmp_path, ontology_version=ontology.version, pack_versions={})
    report = await _run_against(recipe, ontology, _cdr_csv(tmp_path))
    assert report.rows_read == 10


async def test_an_extra_pin_is_ignored(tmp_path: Path) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path, ontology_version=ontology.version, pack_versions={"stix": 99}
    )
    report = await _run_against(recipe, ontology, _cdr_csv(tmp_path))
    assert report.rows_read == 10


async def test_an_extra_pin_on_a_pack_the_ontology_lacks_is_ignored(tmp_path: Path) -> None:
    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path, ontology_version=ontology.version, pack_versions={"nosuchpack": 1}
    )
    report = await _run_against(recipe, ontology, _cdr_csv(tmp_path))
    assert report.rows_read == 10


async def test_a_dry_run_of_an_unpinned_draft_writing_fibo_is_not_refused(
    tmp_path: Path,
) -> None:
    from services.ingest.engine import dry_run_recipe

    from ontology.packs import load_deployment_ontology

    ontology = load_deployment_ontology()
    recipe = _recipe_from_yaml(
        tmp_path,
        ontology_version=ontology.version,
        pack_versions=None,
        domain_pack="pole",
        row_template=_ACCOUNT_TEMPLATE,
    )
    async with arcadedb_adapter(ontology, load_uk_le_scheme()) as graph:
        result = await dry_run_recipe(
            recipe,
            read_csv(_account_csv(tmp_path)),
            graph=graph,
            ontology=ontology,
            principal=CLEARED,
            source="accounts.csv",
        )
    assert result.rows_read == 1
