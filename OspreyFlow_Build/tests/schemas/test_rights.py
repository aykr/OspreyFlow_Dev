"""The rights model (`06_DECISIONS.md` ADR-112): four roles built from named rights. The table below is
ADR-112's own, written out again here by hand — never imported from the code — so a right moved
between roles in one place and not the other fails (rule 12: an invariant stated in prose and
exercised by nothing is this project's recurring failure).
"""

from __future__ import annotations

from schemas.rights import ROLE_RIGHTS, Right, rights_for

A, D, M, R = "analyst", "data_engineer", "osprey-admin", "reports_viewer"

#: ADR-112's rights table, by right: which of the four roles hold it.
TABLE: dict[str, set[str]] = {
    "create_case": {A, D}, "share_case": {A, D, M}, "remove_case": {A, M}, "branch_case": {A},
    "export": {A}, "export_override": {A},
    "investigate": {A, D}, "edit_graph": {A}, "confirm_inferred": {A}, "extract_files": {A},
    "resolve_entities": {A}, "record_assessment": {A}, "ask_model": {A}, "run_analysis": {A, D},
    "propose_link_type": {A, D},
    "read_alert_queue": {A, D, R}, "triage_alerts": {A}, "deploy_rules": {A, D},
    "read_rule_audit": {A, D, M}, "read_held_rows": {A, D}, "decide_held_rows": {A, D},
    "trace_ownership": {A}, "keep_watches": {A}, "load_screening_lists": {D, M},
    "edit_pipelines": {D}, "verify_pipelines": {D}, "publish_pipelines": {D}, "run_pipelines": {D},
    "schedule_pipelines": {D, M}, "add_ingest_files": {A, D}, "revert_loads": {D, M},
    "read_reports": {A, D, R}, "read_report_feed": {R}, "read_data_feeds": {A, D, R},
    "administer_system": {M}, "manage_people": {M}, "manage_dashboards": {M},
    "operate_schedules": {D, M}, "manage_ontology": {M}, "manage_geospatial": {M},
    "read_audit": {M}, "read_export_ledger": {M},
}  # fmt: skip


def test_there_are_forty_two_rights_and_the_table_names_each_once() -> None:
    assert len(Right) == 42
    assert set(TABLE) == {r.value for r in Right}


def test_each_role_holds_exactly_its_column_of_the_table() -> None:
    for role in (A, D, M, R):
        expected = {right for right, holders in TABLE.items() if role in holders}
        assert {r.value for r in ROLE_RIGHTS[role]} == expected, role


def test_a_reports_viewer_can_change_nothing() -> None:
    assert {r.value for r in rights_for([R])} == {"read_alert_queue", "read_reports", "read_report_feed",
                                                   "read_data_feeds"}  # fmt: skip


def test_an_administrator_holds_no_right_to_investigate() -> None:
    held = rights_for([M])
    assert not held & {Right.INVESTIGATE, Right.EDIT_GRAPH, Right.TRIAGE_ALERTS, Right.TRACE_OWNERSHIP,
                       Right.READ_REPORTS, Right.READ_ALERT_QUEUE}  # fmt: skip


def test_a_right_may_be_granted_singly() -> None:
    assert rights_for(["right:read_export_ledger"]) == {Right.READ_EXPORT_LEDGER}
    assert rights_for(["right:not_a_right", "someone-elses-role"]) == frozenset()


def test_the_old_roles_keep_working_for_the_transition() -> None:
    """`source_author`, `source_approver` and `loader` give their own Studio rights, `compliance`
    the export ledger — so a token issued before the realm is migrated loses nothing."""
    assert rights_for(["source_author"]) == {Right.EDIT_PIPELINES, Right.VERIFY_PIPELINES,
                                             Right.ADD_INGEST_FILES}  # R6: it listed and uploaded files
    assert rights_for(["source_approver"]) == {Right.PUBLISH_PIPELINES, Right.SCHEDULE_PIPELINES}
    assert rights_for(["loader"]) == {Right.RUN_PIPELINES}
    assert rights_for(["compliance"]) == {Right.READ_EXPORT_LEDGER}
