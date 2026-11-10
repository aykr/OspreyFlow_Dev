"""ADR-140 Amendment 12, the schemas half of phase 7b (the orchestrator's settlements Q1 (a) and
Q2 (a), 8 November 2026).

What a mistake would do, and the case that catches it:

- a staging step kind the pipeline graph cannot hold, or a pipeline node kind the catalogue does not
  run, so a drawer saves a step nothing reads
  (`test_the_pipeline_s_step_kinds_are_the_staging_catalogue_s`);
- a row key, raw or hashed, travelling on a rejection's refs to the Glass (rule 7)
  (`test_a_rejection_ref_carries_no_row_key`, `test_a_rejection_ref_refuses_any_other_field`);
- a step's counts shown to a reader who may not view every marking the load wrote at (rule 3)
  (`test_step_counts_are_withheld_with_the_other_counts`), or withheld from one who may
  (`test_step_counts_reach_a_reader_who_may_see_the_counts`).
"""

from __future__ import annotations

import typing

import pytest
from pydantic import ValidationError
from services.api.load_records import report_view

from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.ingest import (
    LoadReport,
    LoadReportView,
    PipelineNodeKind,
    RejectionRecord,
    RejectionRef,
    StagingPreview,
    StagingStepCount,
)
from schemas.staging import StagingStep

SCHEME = load_uk_le_scheme()
SECRET_ROW = Handling(
    classification="SECRET", handling_code="P", owning_unit="unit-1", originator="unit-1"
)


def _staging_kinds() -> set[str]:
    union = typing.get_args(typing.get_args(StagingStep)[0])
    return {typing.get_args(m.model_fields["kind"].annotation)[0] for m in union}


def test_the_pipeline_s_step_kinds_are_the_staging_catalogue_s() -> None:
    staged = {k.value for k in PipelineNodeKind} - {
        "domain_model", "source", "profile", "map", "extract", "enrich", "load",
    }  # fmt: skip
    assert staged == _staging_kinds() == {
        "lookup", "join", "filter", "derive", "union", "dedupe", "sql", "fuzzy_match",
    }  # fmt: skip


def test_a_rejection_ref_carries_no_row_key() -> None:
    # Rule 7: the table, the row number, the load and a Join's side; nothing that is, or is made
    # from, the row's key.
    assert set(RejectionRef.model_fields) == {"table", "row_index", "load_id", "side"}
    for model in (RejectionRef, RejectionRecord, StagingStepCount, LoadReportView, StagingPreview):
        for name in model.model_fields:
            assert "key" not in name and "hash" not in name, (model.__name__, name)


def test_a_rejection_ref_refuses_any_other_field() -> None:
    with pytest.raises(ValidationError):
        RejectionRef.model_validate(
            {"table": "visit_bookings", "row_index": 0, "row_key": "ab12"}
        )


def _report() -> LoadReport:
    return LoadReport(
        load_id="ld-1",
        recipe_id="r-1",
        recipe_version=1,
        rows_read=4,
        markings=[SECRET_ROW],
        staging_steps=[StagingStepCount(step="joined", kind="join", rows_in=4, rows_out=3)],
        rejections=[
            RejectionRecord(
                row_index=2,
                reason="staging step joined (left side, visit_bookings row 2): no key",
                sample="",
                refs=[
                    RejectionRef(
                        table="visit_bookings", row_index=2, load_id="ld-vb", side="left"
                    )
                ],
            )
        ],
    )


def test_step_counts_are_withheld_with_the_other_counts() -> None:
    official = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1")
    view = report_view(_report(), official, SCHEME)
    assert view.withheld
    assert view.staging_steps == []
    assert view.rejections == []


def test_step_counts_reach_a_reader_who_may_see_the_counts() -> None:
    secret = Principal(id="r", clearance="SECRET", org_unit="unit-1")
    view = report_view(_report(), secret, SCHEME)
    assert not view.withheld
    assert [(s.step, s.rows_in, s.rows_out) for s in view.staging_steps] == [("joined", 4, 3)]
    assert view.rejections[0].refs == [
        RejectionRef(table="visit_bookings", row_index=2, load_id="ld-vb", side="left")
    ]
