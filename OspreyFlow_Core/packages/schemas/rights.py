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

from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import BaseModel


class Right(StrEnum):
    # Cases
    CREATE_CASE = "create_case"  # C1
    SHARE_CASE = "share_case"  # C2, Author (the administrator's safety net: an orphaned case)
    REMOVE_CASE = "remove_case"  # C3, Author
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
    # ADR-112 Amendment 4 (ADR-145 decision 7): the Analyst's three drawing rights. Each route
    # arrives with its own step (boards, promotion, proposed types); a role holding
    # `promote_to_dataset` and `review_promotions`, or `propose_types` and `accept_types`, is
    # refused (`FORBIDDEN_PAIRS`).
    DRAW_ON_BOARDS = "draw_on_boards"  # I11, Editor
    PROMOTE_TO_DATASET = "promote_to_dataset"  # I12, Author
    PROPOSE_TYPES = "propose_types"  # I13, Editor
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
    # ADR-112 Amendment 5 decision 1: write, test and make live rules and hotlists in Rules and
    # Monitoring. Opens that place; its routes are the rules lane's (L2.9).
    AUTHOR_RULES = "author_rules"  # L10
    # ADR-139 decision 3: propose and approve (a second person) installation-wide link-strength
    # influencers.
    MANAGE_STRENGTH_INFLUENCERS = "manage_strength_influencers"  # I10
    # Ingest
    EDIT_PIPELINES = "edit_pipelines"  # D1, Editor
    VERIFY_PIPELINES = "verify_pipelines"  # D2, Editor
    PUBLISH_PIPELINES = "publish_pipelines"  # D3, Editor
    RUN_PIPELINES = "run_pipelines"  # D4, Editor
    SCHEDULE_PIPELINES = "schedule_pipelines"  # D5, Editor
    ADD_INGEST_FILES = "add_ingest_files"  # D6, Editor
    REVERT_LOADS = "revert_loads"  # D7, Editor
    # ADR-140 decision 4: edit a dataset's domain model (its draft, impact, *Make live*, revert).
    EDIT_TARGET_MODEL = "edit_target_model"  # D8, behind the dataset's own gate
    # ADR-112 Amendment 4: review an analyst's promotion into a dataset, as its second person (the
    # dataset's promotion policy, ADR-145 decision 8). Held by the Data Engineer; the other four
    # rights that amendment names arrive with their own steps.
    REVIEW_PROMOTIONS = "review_promotions"  # D9
    # ADR-112 Amendment 4: accept a proposed type into a dataset's domain model (the Data
    # Engineer), the second half of `propose_types`. Its route arrives with proposed types.
    ACCEPT_TYPES = "accept_types"  # D10
    # ADR-112 Amendment 5 decision 1: merge a drawn dataset into another in the Studio (ADR-143
    # Amendment 2). Held by the Data Engineer; its route arrives with the merge (L3.4).
    MERGE_DATASETS = "merge_datasets"  # D11
    # ADR-140 decision 3 (the redesign's phase 8): write the expert steps, a SQL transform and a
    # fuzzy match, in expert mode. Granted by an administrator, singly
    # (`right:write_sql_transforms`) or in a custom role; no built-in role holds it (ADR-112
    # Amendment 8).
    WRITE_SQL_TRANSFORMS = "write_sql_transforms"  # D12
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
    # ADR-112 Amendment 7 (ADR-135 Amendment 2): model engines, each job's model and their keys.
    MANAGE_MODELS = "manage_models"  # A9


R = Right
ANALYST = frozenset({
    R.CREATE_CASE, R.SHARE_CASE, R.REMOVE_CASE, R.EXPORT, R.EXPORT_OVERRIDE,
    R.INVESTIGATE, R.EDIT_GRAPH, R.CONFIRM_INFERRED, R.EXTRACT_FILES, R.RESOLVE_ENTITIES,
    R.RECORD_ASSESSMENT, R.ASK_MODEL, R.RUN_ANALYSIS, R.PROPOSE_LINK_TYPE,
    R.DRAW_ON_BOARDS, R.PROMOTE_TO_DATASET, R.PROPOSE_TYPES,
    R.READ_ALERT_QUEUE, R.TRIAGE_ALERTS, R.DEPLOY_RULES, R.READ_RULE_AUDIT, R.READ_HELD_ROWS,
    R.DECIDE_HELD_ROWS, R.TRACE_OWNERSHIP, R.KEEP_WATCHES, R.MANAGE_STRENGTH_INFLUENCERS,
    R.ADD_INGEST_FILES, R.READ_REPORTS, R.READ_DATA_FEEDS,
})  # fmt: skip
DATA_ENGINEER = frozenset({
    R.CREATE_CASE, R.SHARE_CASE, R.INVESTIGATE, R.RUN_ANALYSIS, R.PROPOSE_LINK_TYPE,
    R.READ_ALERT_QUEUE, R.DEPLOY_RULES, R.READ_RULE_AUDIT, R.READ_HELD_ROWS, R.DECIDE_HELD_ROWS,
    R.LOAD_SCREENING_LISTS,
    R.EDIT_PIPELINES, R.VERIFY_PIPELINES, R.PUBLISH_PIPELINES, R.RUN_PIPELINES,
    R.SCHEDULE_PIPELINES, R.ADD_INGEST_FILES, R.REVERT_LOADS, R.EDIT_TARGET_MODEL,
    R.REVIEW_PROMOTIONS, R.ACCEPT_TYPES, R.MERGE_DATASETS, R.READ_REPORTS, R.READ_DATA_FEEDS,
    R.OPERATE_SCHEDULES,
})  # fmt: skip
ADMIN = frozenset({
    R.SHARE_CASE, R.REMOVE_CASE, R.READ_RULE_AUDIT, R.LOAD_SCREENING_LISTS, R.SCHEDULE_PIPELINES,
    R.REVERT_LOADS, R.ADMINISTER_SYSTEM, R.MANAGE_PEOPLE, R.MANAGE_DASHBOARDS, R.OPERATE_SCHEDULES,
    R.MANAGE_ONTOLOGY, R.MANAGE_GEOSPATIAL, R.READ_AUDIT, R.READ_EXPORT_LEDGER,
    R.MANAGE_STRENGTH_INFLUENCERS, R.MANAGE_MODELS,
})  # fmt: skip
REPORTS_VIEWER = frozenset(
    {R.READ_ALERT_QUEUE, R.READ_REPORTS, R.READ_REPORT_FEED, R.READ_DATA_FEEDS}
)

#: ADR-112 Amendment 5 decision 2: works alerts and writes rules; holds no Studio right. It reads
#: the alert queue, since whoever triages must (the owner's ruling on L2.9 Q1 (a), 8 November 2026;
#: ADR-146 Amendment 2 point 5), so Rules and Monitoring's entry read answers it.
RULE_AUTHOR = frozenset({R.AUTHOR_RULES, R.TRIAGE_ALERTS, R.READ_ALERT_QUEUE})

#: The built-in roles: ADR-112's four and Amendment 5's *Rule author*, by the name the identity
#: provider gives them. None can be edited, only copied into a custom role (Amendment 4).
ROLE_RIGHTS: dict[str, frozenset[Right]] = {
    "analyst": ANALYST,
    "data_engineer": DATA_ENGINEER,
    "osprey-admin": ADMIN,
    "reports_viewer": REPORTS_VIEWER,
    "rule_author": RULE_AUTHOR,
}

#: The *Super user* preset (ADR-145 decision 7, ADR-112 Amendment 5 decision 2): Analyst, Data
#: Engineer and `author_rules`, given as these three roles together, never as one role, so that no
#: role holds both halves of a `FORBIDDEN_PAIRS` pair (the owner's ruling of 8 November 2026, L2.5
#: Q2 (a)). A person given it still cannot be the second person on their own work.
SUPER_USER_PRESET: tuple[str, ...] = ("analyst", "data_engineer", "rule_author")

#: ADR-145 decision 7 and ADR-112 Amendment 5 decision 6: no role both proposes and approves the
#: same kind of decision. A custom role holding both rights of a pair is refused at the route.
FORBIDDEN_PAIRS: tuple[tuple[Right, Right], ...] = (
    (R.PROMOTE_TO_DATASET, R.REVIEW_PROMOTIONS),
    (R.PROPOSE_TYPES, R.ACCEPT_TYPES),
)

#: The roles before ADR-112, each kept to the rights it already conferred, for the transition.
LEGACY_ROLE_RIGHTS: dict[str, frozenset[Right]] = {
    # `source_author` also listed and uploaded ingest files (owner ruling R6), so it keeps that too.
    "source_author": frozenset({R.EDIT_PIPELINES, R.VERIFY_PIPELINES, R.ADD_INGEST_FILES}),
    "source_approver": frozenset({R.PUBLISH_PIPELINES, R.SCHEDULE_PIPELINES}),
    "loader": frozenset({R.RUN_PIPELINES}),
    "compliance": frozenset({R.READ_EXPORT_LEDGER}),
}

#: The administration rights (A1-A9): a custom role may hold one, and a person be given one, only
#: by someone who holds it, so that a holder of `manage_people` alone cannot give themselves
#: `administer_system` (ADR-145 Amendment 5, pending the owner's answer to L2.5 Q3b).
ADMINISTRATION_RIGHTS = frozenset({
    R.ADMINISTER_SYSTEM, R.MANAGE_PEOPLE, R.MANAGE_DASHBOARDS, R.OPERATE_SCHEDULES,
    R.MANAGE_ONTOLOGY, R.MANAGE_GEOSPATIAL, R.READ_AUDIT, R.READ_EXPORT_LEDGER, R.MANAGE_MODELS,
})  # fmt: skip

SINGLE_RIGHT_PREFIX = "right:"
#: A custom role (ADR-112 Amendment 4) arrives in the token as `role:<id>`; its rights are its
#: current version's, read from the Conduit's store on each request (the owner's ruling of
#: 8 November 2026, L2.5 Q1 (a)) and passed here as `custom`.
CUSTOM_ROLE_PREFIX = "role:"


def teams_of(roles: Iterable[str]) -> list[str]:
    """The teams a principal is in: each custom role (`role:<id>`) their token carries, sorted
    (ADR-145 Amendment 5 point 5). Read from the request each time, never kept."""
    return sorted(r[len(CUSTOM_ROLE_PREFIX) :] for r in roles if r.startswith(CUSTOM_ROLE_PREFIX))


_BY_VALUE = {r.value: r for r in Right}


def forbidden_pairs_in(rights: Iterable[Right | str]) -> list[tuple[Right, Right]]:
    """Each `FORBIDDEN_PAIRS` pair the set holds whole."""
    held = {str(r) for r in rights}
    return [(a, b) for a, b in FORBIDDEN_PAIRS if a.value in held and b.value in held]


def rights_for(
    roles: Iterable[str], custom: Mapping[str, Iterable[Right]] | None = None
) -> frozenset[Right]:
    """Every right the token's roles confer: each role's bundle, each old role's own rights, each
    right granted singly, and each custom role's current rights where `custom` (role id to rights)
    is given. A role this deployment does not know confers nothing; a custom role absent from
    `custom` (removed, or not read) confers nothing either."""
    held: set[Right] = set()
    for role in roles:
        held |= ROLE_RIGHTS.get(role, frozenset()) | LEGACY_ROLE_RIGHTS.get(role, frozenset())
        if role.startswith(SINGLE_RIGHT_PREFIX) and role[len(SINGLE_RIGHT_PREFIX) :] in _BY_VALUE:
            held.add(_BY_VALUE[role[len(SINGLE_RIGHT_PREFIX) :]])
        if custom is not None and role.startswith(CUSTOM_ROLE_PREFIX):
            held |= set(custom.get(role[len(CUSTOM_ROLE_PREFIX) :], ()))
    return frozenset(held)


class RightsResponse(BaseModel):
    """`GET /v1/me/rights`: what the signed-in person may do, so the Glass and the Studio can leave
    out what they would only refuse. The Conduit still refuses it (decision 1)."""

    rights: list[Right]


ALL_MODELS = [RightsResponse]
