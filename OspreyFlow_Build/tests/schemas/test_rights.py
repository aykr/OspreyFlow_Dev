"""The rights model (`06_DECISIONS.md` ADR-112): four roles built from named rights. The table below is
ADR-112's own, written out again here by hand — never imported from the code — so a right moved
between roles in one place and not the other fails (rule 12: an invariant stated in prose and
exercised by nothing is this project's recurring failure).
"""

from __future__ import annotations

from schemas.rights import (
    FORBIDDEN_PAIRS,
    ROLE_RIGHTS,
    SUPER_USER_PRESET,
    Right,
    forbidden_pairs_in,
    rights_for,
)

A, D, M, R = "analyst", "data_engineer", "osprey-admin", "reports_viewer"
#: ADR-112 Amendment 5 decision 2's *Rule author*.
U = "rule_author"

#: ADR-112's rights table, by right: which of the four roles hold it.
TABLE: dict[str, set[str]] = {
    "create_case": {A, D}, "share_case": {A, D, M}, "remove_case": {A, M},
    "export": {A}, "export_override": {A},
    "investigate": {A, D}, "edit_graph": {A}, "confirm_inferred": {A}, "extract_files": {A},
    "resolve_entities": {A}, "record_assessment": {A}, "ask_model": {A}, "run_analysis": {A, D},
    "propose_link_type": {A, D},
    # ADR-112 Amendment 4: the Analyst's drawing rights, and the Data Engineer's type acceptance.
    "draw_on_boards": {A}, "promote_to_dataset": {A}, "propose_types": {A}, "accept_types": {D},
    # ADR-112 Amendment 5 decisions 1 and 2: the Rule author's right; the drawn-dataset merge.
    "author_rules": {U}, "merge_datasets": {D},
    "read_alert_queue": {A, D, R, U}, "triage_alerts": {A, U}, "deploy_rules": {A, D},
    "read_rule_audit": {A, D, M}, "read_held_rows": {A, D}, "decide_held_rows": {A, D},
    "trace_ownership": {A}, "keep_watches": {A}, "load_screening_lists": {D, M},
    # ADR-139 decision 3: analysts propose and approve; the administrator too (Amendment 1).
    "manage_strength_influencers": {A, M},
    "edit_pipelines": {D}, "verify_pipelines": {D}, "publish_pipelines": {D}, "run_pipelines": {D},
    "schedule_pipelines": {D, M}, "add_ingest_files": {A, D}, "revert_loads": {D, M},
    # ADR-140 decision 4 (D8): the domain model's editor, the developer.
    "edit_target_model": {D},
    # ADR-112 Amendment 4 (D9): a promotion's second person, the developer.
    "review_promotions": {D},
    # ADR-112 Amendment 8 (D12): the expert steps, granted singly by an administrator; no role.
    "write_sql_transforms": set(),
    "read_reports": {A, D, R}, "read_report_feed": {R}, "read_data_feeds": {A, D, R},
    "administer_system": {M}, "manage_people": {M}, "manage_dashboards": {M},
    "operate_schedules": {D, M}, "manage_ontology": {M}, "manage_geospatial": {M},
    "read_audit": {M}, "read_export_ledger": {M},
    # ADR-112 Amendment 7 (A9): model engines, each job's model and their keys.
    "manage_models": {M},
}  # fmt: skip


def test_there_are_fifty_two_rights_and_the_table_names_each_once() -> None:
    """Fifty-two until L3.2 removed `branch_case` with its routes (ADR-144 Amendment 1); fifty-two
    again with `write_sql_transforms` (ADR-112 Amendment 8, phase 8)."""
    assert len(Right) == 52
    assert set(TABLE) == {r.value for r in Right}


def test_each_role_holds_exactly_its_column_of_the_table() -> None:
    assert set(ROLE_RIGHTS) == {A, D, M, R, U}
    for role in (A, D, M, R, U):
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


def test_the_rule_author_writes_rules_and_works_alerts_and_holds_no_studio_right() -> None:
    """ADR-112 Amendment 5 decision 2: `author_rules` and `triage_alerts`, with `read_alert_queue`
    since the owner's ruling on L2.9 Q1 (a), 8 November 2026 (ADR-146 Amendment 2 point 5): whoever
    triages reads the queue. Nothing of the Studio's (planted red: `RULE_AUTHOR` given
    `edit_pipelines`)."""
    held = rights_for([U])
    assert held == {Right.AUTHOR_RULES, Right.TRIAGE_ALERTS, Right.READ_ALERT_QUEUE}
    studio = {Right.EDIT_PIPELINES, Right.VERIFY_PIPELINES, Right.PUBLISH_PIPELINES,
              Right.RUN_PIPELINES, Right.SCHEDULE_PIPELINES, Right.EDIT_TARGET_MODEL,
              Right.MERGE_DATASETS, Right.ACCEPT_TYPES, Right.REVIEW_PROMOTIONS}  # fmt: skip
    assert not held & studio


def test_the_analyst_reads_rules_but_does_not_author_them() -> None:
    assert Right.AUTHOR_RULES not in rights_for([A])
    assert Right.TRIAGE_ALERTS in rights_for([A])


def test_the_super_user_preset_is_three_roles_and_gains_author_rules() -> None:
    """ADR-145 decision 7 (Analyst + Data Engineer) and Amendment 5 decision 2 (+ `author_rules`),
    given as three roles (the owner's L2.5 Q2 (a)), so that no one role holds a forbidden pair."""
    assert SUPER_USER_PRESET == ("analyst", "data_engineer", "rule_author")
    assert rights_for(SUPER_USER_PRESET) == ROLE_RIGHTS[A] | ROLE_RIGHTS[D] | {Right.AUTHOR_RULES,
                                                                               Right.TRIAGE_ALERTS}  # fmt: skip


def test_no_built_in_role_both_proposes_and_approves() -> None:
    """ADR-145 decision 7: the pairs, written out here by hand, and no built-in role holding one."""
    assert {(a.value, b.value) for a, b in FORBIDDEN_PAIRS} == {
        ("promote_to_dataset", "review_promotions"), ("propose_types", "accept_types")}
    for role, rights in ROLE_RIGHTS.items():
        assert forbidden_pairs_in(rights) == [], role


def test_a_custom_role_confers_exactly_its_given_rights_and_only_when_read() -> None:
    """ADR-112 Amendment 4 as ruled (L2.5 Q1 (a)): `role:<id>` confers its current version's
    rights, passed in from the store; unread or removed, nothing."""
    given = {"r7": [Right.READ_REPORTS, Right.RUN_ANALYSIS]}
    assert rights_for(["role:r7"], given) == {Right.READ_REPORTS, Right.RUN_ANALYSIS}
    assert rights_for(["role:r7"]) == frozenset()
    assert rights_for(["role:r8"], given) == frozenset()


def test_the_administration_rights_are_the_a_rights() -> None:
    """ADR-145 Amendment 5: the rights only a holder may give, written out by hand."""
    from schemas.rights import ADMINISTRATION_RIGHTS

    assert {r.value for r in ADMINISTRATION_RIGHTS} == {
        "administer_system", "manage_people", "manage_dashboards", "operate_schedules",
        "manage_ontology", "manage_geospatial", "read_audit", "read_export_ledger", "manage_models"}  # fmt: skip
