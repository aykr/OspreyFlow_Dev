"""ADR-110 Amendment 16, rule 3: a link's prior state is graph data. Its properties, sources and
marking are held in the run ledger for the revert alone, and nothing a reader is given carries
them: not the load's report, as dumped or as `report_view` answers it, alone or as a pipeline's
branch; not `LoadReport`'s schema, from which the workspace's types are generated; not the run's
metering. Each is checked for a sentinel written into the prior state. Red with the field exposed
(`LoadReport.own_key_merges` without `exclude`, `process/lanes/studio/L1.2a_RED_RECORD.md`). The
run ledger's own round trip, and the run view read from it, are
`test_row_key_withdrawal_ledger.py`'s, against real Postgres."""

from __future__ import annotations

import json

from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.ingest import (
    BranchRunReport,
    LinkPriorState,
    LoadReport,
    PipelineRunReport,
)
from services.api.load_records import report_view
from services.ingest.metering import metering_of

SCHEME = load_uk_le_scheme()
SENTINEL = "PRIOR-STATE-SENTINEL"
READER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def prior() -> LinkPriorState:
    return LinkPriorState(
        edge_id="link-1",
        edge_type="TRANSACTED",
        revision=1,
        load_id="load-1",
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        stored={"properties": {"memo": SENTINEL}, "provenance": {"sources": [SENTINEL]}},
    )


def report() -> LoadReport:
    return LoadReport(
        load_id="load-3", recipe_id="private-cash", recipe_version=1, rows_read=2,
        merged_edge_ids=["link-1"], own_key_merges=[prior()],
    )  # fmt: skip


def test_a_loads_report_never_carries_a_links_prior_state() -> None:
    held = report()
    assert held.own_key_merges == [prior()], "kept for the ledger"
    assert SENTINEL not in held.model_dump_json()
    assert "own_key_merges" not in json.dumps(LoadReport.model_json_schema())
    assert SENTINEL not in report_view(held, READER, SCHEME).model_dump_json()


def test_a_pipelines_report_never_carries_a_branchs_prior_state() -> None:
    pipeline = PipelineRunReport(
        load_id="run-1", recipe_id="private-cash", recipe_version=1,
        branches=[BranchRunReport(source_id="cash", source_label="Cash", report=report())],
    )  # fmt: skip
    assert SENTINEL not in pipeline.model_dump_json()
    assert "own_key_merges" not in json.dumps(PipelineRunReport.model_json_schema())
    assert SENTINEL not in report_view(pipeline, READER, SCHEME).model_dump_json()


def test_a_runs_metering_never_carries_a_links_prior_state() -> None:
    metering = metering_of(report(), wall_seconds=0.1, object_store_bytes=0)
    assert SENTINEL not in metering.model_dump_json()
