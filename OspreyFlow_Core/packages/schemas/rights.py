"""Rights and roles (`06_DECISIONS.md` ADR-112): what a person may *do*.

**A right is a named action, never a licence to see.** What a person sees when they act is still
decided by their clearance and the case's datasets, in the adapter (rule 3); inside a case a right
also needs the case grant (ADR-052). Every right is checked in the Conduit (`require_right`), never
only in the interface.

**A role is a bundle of rights,** arriving in the token's `roles` claim from the identity provider:
`analyst`, `data_engineer`, `osprey-admin` (the realm's administrator role keeps the name the
harness and the Conduit already use) and `reports_viewer`. A right may also be granted singly, as a
role named `right:<name>`. The roles before ADR-112 keep their rights for the transition:
`source_author`, `source_approver` and `loader` their own Studio rights, `compliance` the export
ledger.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel


class Right(StrEnum):
    # Cases
    CREATE_CASE = "create_case"  # C1
    SHARE_CASE = "share_case"  # C2, Author (the administrator's safety net: an orphaned case)
    REMOVE_CASE = "remove_case"  # C3, Author
    BRANCH_CASE = "branch_case"  # C4, Editor
    EXPORT = "export"  # C5, Editor, through the export gate
    EXPORT_OVERRIDE = "export_override"  # C6, Editor: a consult-originator item, justified
    # Investigation
    INVESTIGATE = "investigate"  # I1, Viewer: search, expand, paths, filters
    EDIT_GRAPH = "edit_graph"  # I2, Editor
    CONFIRM_INFERRED = "confirm_inferred"  # I3, Editor
    EXTRACT_FILES = "extract_files"  # I4, Editor: add files, run extraction, decide findings
    RESOLVE_ENTITIES = "resolve_entities"  # I5, Editor
    RECORD_ASSESSMENT = "record_assessment"  # I6, Editor: judgements, gaps, assumptions
    ASK_MODEL = "ask_model"  # I7, Viewer
    RUN_ANALYSIS = "run_analysis"  # I8, Viewer
    PROPOSE_LINK_TYPE = "propose_link_type"  # I9, Editor
    # Alerts and AML
    READ_ALERT_QUEUE = "read_alert_queue"  # L1, Viewer
    TRIAGE_ALERTS = "triage_alerts"  # L2, Editor
    DEPLOY_RULES = "deploy_rules"  # L3, Author
    READ_RULE_AUDIT = "read_rule_audit"  # L4, Author
    READ_HELD_ROWS = "read_held_rows"  # L5, Editor
    DECIDE_HELD_ROWS = "decide_held_rows"  # L6, Author
    TRACE_OWNERSHIP = "trace_ownership"  # L7, Viewer: ownership, due diligence, neighbourhood risk
    KEEP_WATCHES = "keep_watches"  # L8, Editor: watchlists and saved-pattern monitors
    LOAD_SCREENING_LISTS = "load_screening_lists"  # L9, licensed lists only
    # Ingest
    EDIT_PIPELINES = "edit_pipelines"  # D1, Editor
    VERIFY_PIPELINES = "verify_pipelines"  # D2, Editor
    PUBLISH_PIPELINES = "publish_pipelines"  # D3, Editor
    RUN_PIPELINES = "run_pipelines"  # D4, Editor
    SCHEDULE_PIPELINES = "schedule_pipelines"  # D5, Editor
    ADD_INGEST_FILES = "add_ingest_files"  # D6, Editor
    REVERT_LOADS = "revert_loads"  # D7, Editor
    # Reporting
    READ_REPORTS = "read_reports"  # R1, Viewer
    READ_REPORT_FEED = "read_report_feed"  # R2, Viewer
    READ_DATA_FEEDS = "read_data_feeds"  # R3, Viewer
    # Administration
    ADMINISTER_SYSTEM = "administer_system"  # A1
    MANAGE_PEOPLE = "manage_people"  # A2
    MANAGE_DASHBOARDS = "manage_dashboards"  # A3
    OPERATE_SCHEDULES = "operate_schedules"  # A4
    MANAGE_ONTOLOGY = "manage_ontology"  # A5
    MANAGE_GEOSPATIAL = "manage_geospatial"  # A6
    READ_AUDIT = "read_audit"  # A7
    READ_EXPORT_LEDGER = "read_export_ledger"  # A8


R = Right
ANALYST = frozenset({
    R.CREATE_CASE, R.SHARE_CASE, R.REMOVE_CASE, R.BRANCH_CASE, R.EXPORT, R.EXPORT_OVERRIDE,
    R.INVESTIGATE, R.EDIT_GRAPH, R.CONFIRM_INFERRED, R.EXTRACT_FILES, R.RESOLVE_ENTITIES,
    R.RECORD_ASSESSMENT, R.ASK_MODEL, R.RUN_ANALYSIS, R.PROPOSE_LINK_TYPE,
    R.READ_ALERT_QUEUE, R.TRIAGE_ALERTS, R.DEPLOY_RULES, R.READ_RULE_AUDIT, R.READ_HELD_ROWS,
    R.DECIDE_HELD_ROWS, R.TRACE_OWNERSHIP, R.KEEP_WATCHES,
    R.ADD_INGEST_FILES, R.READ_REPORTS, R.READ_DATA_FEEDS,
})  # fmt: skip
DATA_ENGINEER = frozenset({
    R.CREATE_CASE, R.SHARE_CASE, R.INVESTIGATE, R.RUN_ANALYSIS, R.PROPOSE_LINK_TYPE,
    R.READ_ALERT_QUEUE, R.DEPLOY_RULES, R.READ_RULE_AUDIT, R.READ_HELD_ROWS, R.DECIDE_HELD_ROWS,
    R.LOAD_SCREENING_LISTS,
    R.EDIT_PIPELINES, R.VERIFY_PIPELINES, R.PUBLISH_PIPELINES, R.RUN_PIPELINES,
    R.SCHEDULE_PIPELINES, R.ADD_INGEST_FILES, R.REVERT_LOADS,
    R.READ_REPORTS, R.READ_DATA_FEEDS, R.OPERATE_SCHEDULES,
})  # fmt: skip
ADMIN = frozenset({
    R.SHARE_CASE, R.REMOVE_CASE, R.READ_RULE_AUDIT, R.LOAD_SCREENING_LISTS, R.SCHEDULE_PIPELINES,
    R.REVERT_LOADS, R.ADMINISTER_SYSTEM, R.MANAGE_PEOPLE, R.MANAGE_DASHBOARDS, R.OPERATE_SCHEDULES,
    R.MANAGE_ONTOLOGY, R.MANAGE_GEOSPATIAL, R.READ_AUDIT, R.READ_EXPORT_LEDGER,
})  # fmt: skip
REPORTS_VIEWER = frozenset(
    {R.READ_ALERT_QUEUE, R.READ_REPORTS, R.READ_REPORT_FEED, R.READ_DATA_FEEDS}
)

#: The four roles of ADR-112, by the name the identity provider gives them.
ROLE_RIGHTS: dict[str, frozenset[Right]] = {
    "analyst": ANALYST,
    "data_engineer": DATA_ENGINEER,
    "osprey-admin": ADMIN,
    "reports_viewer": REPORTS_VIEWER,
}

#: The roles before ADR-112, each kept to the rights it already conferred, for the transition.
LEGACY_ROLE_RIGHTS: dict[str, frozenset[Right]] = {
    # `source_author` also listed and uploaded ingest files (owner ruling R6), so it keeps that too.
    "source_author": frozenset({R.EDIT_PIPELINES, R.VERIFY_PIPELINES, R.ADD_INGEST_FILES}),
    "source_approver": frozenset({R.PUBLISH_PIPELINES, R.SCHEDULE_PIPELINES}),
    "loader": frozenset({R.RUN_PIPELINES}),
    "compliance": frozenset({R.READ_EXPORT_LEDGER}),
}

SINGLE_RIGHT_PREFIX = "right:"
_BY_VALUE = {r.value: r for r in Right}


def rights_for(roles: Iterable[str]) -> frozenset[Right]:
    """Every right the token's roles confer: each role's bundle, each old role's own rights, and
    each right granted singly. A role this deployment does not know confers nothing."""
    held: set[Right] = set()
    for role in roles:
        held |= ROLE_RIGHTS.get(role, frozenset()) | LEGACY_ROLE_RIGHTS.get(role, frozenset())
        if role.startswith(SINGLE_RIGHT_PREFIX) and role[len(SINGLE_RIGHT_PREFIX) :] in _BY_VALUE:
            held.add(_BY_VALUE[role[len(SINGLE_RIGHT_PREFIX) :]])
    return frozenset(held)


class RightsResponse(BaseModel):
    """`GET /v1/me/rights`: what the signed-in person may do, so the Glass and the Studio can leave
    out what they would only refuse. The Conduit still refuses it (decision 1)."""

    rights: list[Right]


ALL_MODELS = [RightsResponse]
