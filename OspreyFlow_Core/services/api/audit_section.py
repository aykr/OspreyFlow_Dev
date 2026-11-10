"""Admin › Audit (`06_DECISIONS.md` ADR-145 decision 10, O2; Amendment 3 decision 1; ADR-112
Amendment 7 decision 7; ADR-146 Amendment 2: the rule audit returns here for the Administrator).

One view over the records that already exist, read under the reader's own principal (rule 3):

- **The audit stream** (`audit_log`, written by `AuditWriter.record` on every route): the case
  audit, the people, roles and dataset audits, and the loads. An entry is the reader's unit's when
  the case it names is owned by that unit, or, naming no case, when it was written by an account of
  that unit (`audit_log.org_unit`, from L2.6). **The unit filter is in the `WHERE` clause** (rule
  3), so another unit's entry is neither on the page nor in the total; a filter is only ever ANDed
  after it, so a filter never widens the read. An entry naming a case that does not exist, or
  written before `org_unit` and naming no case, belongs to no unit and is never shown (fail closed).
- **The rule audit** (ADR-109 ruling 1) is never read here from the stream: its entries carry words
  (a firing's) that `rule_holds.readable_rule_audit` withholds entry by entry as the reader. They
  are left out of the stream's read entirely, and the `rules` record is served by that read itself,
  for one case, behind the gate the case's own rule-audit route uses (`app.py`).
- **The engines' history** (`model_admin_audit`): ADR-112 Amendment 7 decision 7 names it as read
  here under `read_audit`. Engines are the deployment's, not a unit's, and the history never holds
  a key, so every holder of `read_audit` reads it whole.

**The words an entry holds.** No read of the stream existed before this one to decide what an
entry's `resolved_query` may tell, and it can name nodes, documents and queries. So its words and
its count are withheld (`words_withheld`), except for the two kinds whose words the reader's own
section already shows them: *People and roles* to a holder of `manage_people`, *Datasets* to a
holder of `administer_system`. Its existence (who, when, which action, which case of their own unit)
is shown, as ADR-052 §4 lets an administrator of the unit see its cases.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg

from schemas.admin import AuditKind, AuditSectionEntry
from schemas.domain import Principal
from schemas.rights import Right

from .investigations import TEAM_GRANT_PREFIX
from .rule_evaluation import RULE_AUDIT_ACTIONS

#: Decision 10's kinds, by the actions the audit stream records under each. An action in none of
#: them reads as `reads_and_other`; the rule audit's own actions are never read from the stream.
KIND_ACTIONS: dict[str, tuple[str, ...]] = {
    "assertions": (
        "confirm_node",
        "retract_node",
        "manual_link",
        "manual_split",
        "link_change",
        "link_note_add",
        "link_note_edit",
        "link_note_remove",
        "judgement_save",
        "assumption_save",
        "gap_save",
        "designate_in_document",
        "accept_extraction_candidate",
        "accept_document_candidate",
        "accept_document_candidates",
        "accept_email_candidate",
        "accept_question_candidate",
        "reject_extraction_candidate",
        "reject_document_candidate",
        "reject_email_candidate",
        "reject_question_candidate",
        "set_entity_picture",
        "remove_entity_picture",
        "mark_node_for_suppression",
        "unmark_node_for_suppression",
        "remove_nodes",
        "resolve_now",
        "draw_item",
        "draw_link",
        "edit_drawn_item",
        "withdraw_drawn_item",
        "set_drawn_picture",
        "choose_drawn_picture",
        "decide_board_match",
    ),
    "loads_and_promotions": (
        "run_studio_recipe",
        "run_schedule_now",
        "publish_studio_recipe",
        "verify_studio_recipe",
        "upload_ingest_source_file",
        # L1.6: a connector's source read into the dataset's ingest file (its own upload).
        "read_connector_source",
        "upload_document",
        "pause_schedule",
        "resume_schedule",
        "change_schedule",
        "pause_recipe_schedule",
        "update_studio_recipe_schedule",
        "pause_source_refresh",
        "screening_list_refreshed",
        "screening_list_subscribed",
        "screening_list_schedule_set",
        # The Studio's deployment lists (L1.6, ADR-140 Amendment 15): added, refreshed, scheduled,
        # subscribed and imported.
        "add_deployment_list",
        "deployment_list_refreshed",
        "deployment_list_schedule_set",
        "dataset_list_subscribed",
        "dataset_list_unsubscribed",
        "import_dataset_own_list",
        "set_promotion_alert_days",
        "load_reverted",
        "resume_recipe_schedule",
        "resume_source_refresh",
        "create_studio_recipe_version",
        "create_studio_recipe_draft",
        "update_studio_recipe_draft",
        "update_studio_recipe_pipeline",
        "update_studio_recipe_pipeline_yaml",
        "update_studio_recipe_row_template",
        # L1.7 (ADR-141 decision 11): a deployed pipeline handed to an orchestrator's client, and
        # taken back.
        "mark_pipeline_owned_externally",
        "clear_pipeline_owned_externally",
        "add_ingest_connection",
        # Case's L3.4 (ADR-143 Amendment 5): promotions of drawn items, their review, rejection
        # and revert (the operator command's, refused or done), and a removed case's layer merged
        # through its read grant (opened, merged, cancelled) or deleted.
        "promote_drawn_items",
        # Case's L3.9 (ADR-143 Amendment 2 decision 6): a drawn dataset merged into another.
        "merge_drawn_dataset",
        "approve_promotion",
        "reject_promotion",
        "promotion_rejected",
        "revert_promotion",
        "revert_promotion_refused",
        "open_layer_merge",
        "merge_layer",
        "cancel_layer_merge",
        "delete_layer",
    ),
    "types": (
        "link_type_propose",
        "link_type_promote",
        "link_type_reject",
        "link_type_withdraw",
        "link_type_retire",
        "link_type_accept",
        "link_type_decline",
        "make_model_live",
        "revert_model",
        "save_model_draft",
        "discard_model_draft",
        "open_model_draft",
    ),
    "people_and_roles": (
        "invite_person",
        "set_person_roles",
        "set_person_access",
        "disable_person",
        "disable_person_incomplete",
        "enable_person",
        "remove_person",
        "reset_person_sign_in",
        "link_organisation_account",
        "create_custom_role",
        "change_custom_role",
        "make_team",
        "set_team_lead",
        "set_team_cover",
        "transfer_owned_item",
        "name_an_author",
        "grant_access",
        "revoke_access",
        "set_unit_level",
    ),
    "datasets": (
        "create_dataset",
        "create_composite_dataset",
        "set_dataset_egress",
        "set_dataset_promotion_policy",
        "change_dataset_owners",
        "set_dataset_owner_setting",
        "register_dataset_source",
        "edit_dataset_source_governance",
        "make_home_case",
        "make_drawn_dataset",
        "set_case_datasets",
        # Platform's P5 (ADR-147 Amendment 2, ruling 6): a gazetteer added to a dataset (its places
        # copied in) and removed. `dataset_id` is shown; the gazetteer's id is no plain word, so
        # it is left out by default.
        "add_dataset_gazetteer",
        "remove_dataset_gazetteer",
        # L1.7: a dataset's release exported, its import planned (`dry_run`) and imported as drafts
        # (ADR-140 Amendment 9 decision 4), and a dataset's or unit's quota of runs a day set
        # (ADR-141 decision 6).
        "export_dataset_release",
        "plan_dataset_release_import",
        "import_dataset_release",
        "set_run_quota",
    ),
}
_CLASSIFIED: tuple[str, ...] = tuple(a for actions in KIND_ACTIONS.values() for a in actions)

#: Every other action the Conduit writes, named so that each one is classified on purpose
#: (`test_audit_kinds.py` finds every action written in `services/` and `scripts/` and fails on one
#: in no list):
#: reads, refusals, the case's own work and the platform's. `kind_of` reads an unnamed one as this
#: kind too, with its words withheld, so a missing name never shows words.
READS_AND_OTHER: tuple[str, ...] = (
    # Case's L3.4: a promotion's Details, the removed cases' list, a merge sheet read again.
    "read_promotion", "list_removed_case_layers", "read_layer_merge",
    # Case's L3.9: a drawn merge's sheet and its dry run, each reading the drawing for a merge.
    "read_drawn_merge_sheet", "dry_run_drawn_merge",
    # Written by scripts, not routes: a seed's case brief, a sweep closing synthetic instants.
    "case_brief_seed", "close_paysim_instants",
    # L3.7 (ADR-143 Amendment 6): the operator's whole-deployment change of grading scheme, run by
    # `scripts/grading_change.py` outside any case; no analyst asserts anything, so not *Analyst
    # assertions*.
    "grading_change",
    # L1.6's refusal and reads: a connector's read refused, a connection tested.
    "connector_read_refused", "test_ingest_connection",
    "dataset_list_subscriptions", "list_deployment_list_imports", "list_deployment_lists",
    "offered_reference_lists",
    # Rules' L2.10 (ADR-146 Amendment 4): the lead's hand-off and Suppress until…, Raise an alert…,
    # a watched pattern's own schedule set, What raises alerts read; with the other alert actions.
    "alert_handed_off", "alert_suppressed", "alert_raised", "monitor_schedule_set",
    "read_alert_sources",
    # Rules-b's L2.11a (ADR-146 decision 3): a rule's .bpmn or .dmn exported.
    "export_rule_file",
    # Rules' L2.11 (ADR-146 decision 3, Amendment 6): the rule editor's datasets read, a draft
    # saved, tested, made live or asked to go live; with the other rule actions.
    "read_rule_datasets", "rule_draft_saved", "rule_tested", "rule_made_live",
    "rule_make_live_proposed",
    "access_admin_override", "access_denied", "add_by_identifiers", "add_pack_item",
    "alert_assigned", "alert_canvas", "alert_claimed", "alert_close_approved",
    "alert_close_proposed", "alert_close_sent_back", "alert_disposed", "alert_released",
    "analytics_cross_filter", "analytics_first_seen", "analytics_geo_bins", "analytics_geometries",
    "analytics_histogram", "analytics_sightings", "ask_question", "case_brief_add_requirement",
    "case_brief_attach", "case_brief_detach", "case_brief_edit_requirement",
    "case_brief_remove_requirement", "case_brief_set_priority", "case_brief_set_status",
    "case_strength_influencers_set", "connections", "create_investigation", "create_pack",
    "create_site", "delete_board", "delete_case_view", "delete_trend",
    "embedded_dashboard_guest_token", "expand", "expand_preview", "explain_alert",
    "explain_resolution_cluster", "explore_busiest_days", "explore_busiest_links",
    "explore_counts", "explore_groups", "explore_most_connected", "explore_starter_questions",
    "explore_starter_run", "explore_whats_new", "export", "export_pack", "extract_document",
    "extract_email", "geospatial_build_basemap", "geospatial_verify_map",
    "get_dataset_source_profile", "get_dossier_document", "get_history", "get_investigation",
    "get_resolution_threshold", "get_site", "get_studio_recipe_draft", "get_studio_recipe_profile",
    "get_studio_recipe_sample_row", "hotlist_audience_changed", "hotlist_match_notified",
    "hotlist_match_suppressed", "hotlists_create", "kyc_status", "links_among", "list_dashboards",
    "list_data_feeds", "list_dataset_cases", "list_dataset_source_files", "list_dataset_sources",
    "list_demo_packs", "list_embedded_dashboards", "list_extraction_candidates", "list_held_rows",
    "list_ingest_source_files", "list_organisation_arrivals", "list_people",
    "list_published_packs", "list_schedule_runs", "list_schedules", "list_screening_lists",
    "list_studio_recipe_drafts", "list_studio_recipe_registry", "make_board", "map_place_search",
    "monitors_create", "neighbourhood_risk", "open_alert_at_address", "ownership_canvas", "paths",
    "patterns_ask", "patterns_preview", "patterns_run", "patterns_save",
    "preview_studio_recipe_element_handling", "preview_studio_recipe_graph",
    "preview_studio_recipe_staging", "preview_trend", "publish_pack", "read_alert_queue",
    "read_alert_queue_counts", "read_audit_section", "read_case_report", "read_disable_plan",
    "read_document", "read_document_file", "read_entity_picture", "read_entity_pictures",
    "read_load_checks", "read_operations_ageing", "read_pack", "read_people_rows",
    "read_studio_recipe_pipeline_yaml", "check_studio_recipe_sql",
    "read_person_ownership",
    "read_published_pack", "read_report_feed", "read_rule_audit", "read_rule_runs",
    "read_rule_versions", "read_trend", "refresh_pack_item", "register_dashboard",
    "remove_dashboard", "remove_investigation", "remove_pack_item", "rename_investigation",
    "reorder_pack", "restore_history_step", "rule_previewed", "run_extraction", "save_case_view",
    "save_trend", "search", "seed", "set_case_domains", "set_resolution_threshold",
    "set_site_control_points", "set_site_grid", "set_tab_state", "share_board", "share_case_view",
    "shared_contacts", "shared_pair_canvas", "show_emails_as_documents", "stream_connect",
    "strength_influencers_approved", "strength_influencers_proposed",
    "strength_influencers_sent_back", "suggest", "trace_ownership", "watch_evaluation_failed",
    "withdraw_pack",
)  # fmt: skip
#: Actions written with a computed suffix (`compute_<metric>`, `dry_run_layer_<merge|delete>`).
READS_AND_OTHER_PREFIXES: tuple[str, ...] = ("compute_", "dry_run_layer_")
#: Classified before their writer is on main; none since case's L3.4. The check that a kind's
#: action is written (`test_every_kinds_action_is_one_the_conduit_records`) leaves these alone.
AWAITED_ACTIONS: frozenset[str] = frozenset()

#: The kinds whose words the reader's own section shows them, and the right that section needs.
WORDS_SHOWN_WITH: dict[str, Right] = {
    "people_and_roles": Right.MANAGE_PEOPLE,
    "datasets": Right.ADMINISTER_SYSTEM,
}

STREAM_KINDS = (*KIND_ACTIONS, "reads_and_other")


def stream_note(cases: bool, units_from: datetime | None) -> str:
    """Said with every page of the stream, so nothing left out is left out silently (rule 2). The
    date is this deployment's own: when its audit began recording the writer's unit."""
    when = (
        units_from.astimezone(UTC).strftime("%-d %B %Y") if units_from is not None
        else "this deployment's audit began recording units"
    )  # fmt: skip
    if not cases:
        # ADR-052 §4: only `osprey-admin` sees the unit's cases without a level on them.
        return (
            "You hold read_audit but are not your unit's administrator, so entries about cases "
            "are not shown to you: only entries that name no case, written by your unit's "
            f"accounts. An entry that names no case and recorded no unit (written before {when}, "
            "or by the system) is not shown either. Who acted is shown by name; an account's "
            "identifier is never shown."
        )
    return (
        "Entries about another unit's cases are not shown. An entry that names no case is shown "
        f"by the unit of the account that wrote it: one written before {when}, or by the system "
        "itself (a reverted load, a map prefetch), recorded no unit of yours and is not shown. "
        "The rule audit is read for one case at a time: choose Rule audit of one case. Who acted "
        "is shown by name; an account's identifier is never shown."
    )


def dataset_ids_of(detail: dict[str, Any]) -> set[str]:
    """The datasets an entry's words name (`dataset_id`, or a list under `dataset_ids`)."""
    out = {str(detail["dataset_id"])} if detail.get("dataset_id") else set()
    many = detail.get("dataset_ids")
    if isinstance(many, list):
        out |= {str(d) for d in many}
    return out


def shown_actions(rights: frozenset[Right] | set[Right]) -> list[str]:
    """The actions whose words this reader is shown: the only entries a dataset filter may look
    into, since it reads those words (a filter must not answer about words it withholds)."""
    return [
        a for kind, actions in KIND_ACTIONS.items() if words_shown(kind, rights) for a in actions
    ]


def kind_of(action: str) -> AuditKind:
    for kind, actions in KIND_ACTIONS.items():
        if action in actions:
            return kind  # type: ignore[return-value]
    return "reads_and_other"


def words_shown(kind: str, rights: frozenset[Right] | set[Right]) -> bool:
    needed = WORDS_SHOWN_WITH.get(kind)
    return needed is not None and needed in rights


@dataclass(frozen=True)
class StreamFilters:
    """Who, what and when, and a case or dataset. Each narrows; none widens (decision 10)."""

    #: The accounts a chosen person's name stands for, resolved by the route from the writers this
    #: reader may already read (`writers`); the Glass sends a name and never an id.
    who: tuple[str, ...] | None = None
    kind: str | None = None
    investigation_id: str | None = None
    dataset_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None


@dataclass(frozen=True)
class StreamRow:
    recorded_at: datetime
    principal_id: str
    action: str
    investigation_id: str | None
    case_name: str | None
    resolved_query: dict[str, Any]
    result_cardinality: int


def _ids(who: tuple[str, ...] | None) -> list[str] | None:
    if isinstance(who, str):  # a bare id would be read as its letters, a filter matching nothing
        raise TypeError("StreamFilters.who is a tuple of account ids, never one string")
    return None if who is None else list(who)


def _kind_clause(kind: str | None, first: int) -> tuple[str, list[Any]]:
    if kind is None:
        return "", []
    if kind == "reads_and_other":
        return f" AND NOT (a.action = ANY(${first}::text[]))", [list(_CLASSIFIED)]
    return f" AND a.action = ANY(${first}::text[])", [list(KIND_ACTIONS[kind])]


class AuditSectionReader:
    """The section's reads, on the Conduit's database (where `audit_log`, `investigations` and
    `model_admin_audit` all live)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> AuditSectionReader:
        return cls(await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3))

    async def close(self) -> None:
        await self._pool.close()

    async def stream(
        self,
        reader: Principal,
        filters: StreamFilters,
        *,
        offset: int,
        limit: int,
        rights: frozenset[Right] | set[Right] = frozenset(),
        cases: bool = False,
    ) -> tuple[list[StreamRow], int]:
        """The reader's unit's entries of the audit stream, newest first, and their total.

        `cases`: whether entries about the unit's cases are read at all — only for the unit's
        administrator (ADR-052 §4's safety net), whom the route names. `rights`: the dataset filter
        looks only into entries whose words these rights show (`shown_actions`), so filtering by a
        dataset never tells which withheld entries name it."""
        where = (
            "FROM audit_log a LEFT JOIN investigations i ON i.id = a.investigation_id "
            # The unit filter (rule 3): a case's entry by its case's unit, any other by its
            # writer's.
            "WHERE ((a.investigation_id IS NOT NULL AND $8::boolean AND i.owning_unit = $1) "
            "    OR (a.investigation_id IS NULL AND a.org_unit = $1)) "
            # The rule audit is read only through its own read (`readable_rule_audit`).
            "AND NOT (a.action = ANY($2::text[])) "
            "AND ($3::text[] IS NULL OR a.principal_id = ANY($3::text[])) "
            "AND ($4::text IS NULL OR a.investigation_id = $4) "
            "AND ($5::text IS NULL OR (a.action = ANY($9::text[]) AND ("
            "    a.resolved_query->>'dataset_id' = $5 "
            "    OR coalesce(a.resolved_query->'dataset_ids', '[]'::jsonb) ? $5))) "
            "AND ($6::timestamptz IS NULL OR a.recorded_at >= $6) "
            "AND ($7::timestamptz IS NULL OR a.recorded_at < $7)"
        )
        args: list[Any] = [
            reader.org_unit, list(RULE_AUDIT_ACTIONS), _ids(filters.who), filters.investigation_id,
            filters.dataset_id, filters.since, filters.until, cases, shown_actions(rights),
        ]  # fmt: skip
        clause, extra = _kind_clause(filters.kind, len(args) + 1)
        where += clause
        args += extra
        async with self._pool.acquire() as conn:
            total = await conn.fetchval(f"SELECT count(*) {where}", *args)
            rows = await conn.fetch(
                "SELECT a.recorded_at, a.principal_id, a.action, a.investigation_id, "
                "a.resolved_query, a.result_cardinality, i.name AS case_name "
                f"{where} ORDER BY a.recorded_at DESC, a.id DESC "
                f"OFFSET ${len(args) + 1} LIMIT ${len(args) + 2}",
                *args, offset, limit,
            )  # fmt: skip
        return [
            StreamRow(
                recorded_at=r["recorded_at"],
                principal_id=r["principal_id"],
                action=r["action"],
                investigation_id=r["investigation_id"],
                case_name=r["case_name"],
                resolved_query=json.loads(r["resolved_query"])
                if isinstance(r["resolved_query"], str)
                else dict(r["resolved_query"] or {}),
                result_cardinality=r["result_cardinality"],
            )
            for r in rows
        ], int(total or 0)

    async def units_from(self) -> datetime | None:
        async with self._pool.acquire() as conn:
            if await conn.fetchval("SELECT to_regclass('audit_log_units_from')") is None:
                return None
            found = await conn.fetchval("SELECT recorded_from FROM audit_log_units_from")
        return found if isinstance(found, datetime) else None

    async def writers(self, reader: Principal, *, cases: bool) -> set[str]:
        """Who wrote the entries of the stream this reader may read, under the same unit filter
        and rule-audit exclusion as `stream` and no other: the people its picker offers, by name."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT a.principal_id FROM audit_log a "
                "LEFT JOIN investigations i ON i.id = a.investigation_id "
                "WHERE ((a.investigation_id IS NOT NULL AND $3::boolean AND i.owning_unit = $1) "
                "    OR (a.investigation_id IS NULL AND a.org_unit = $1)) "
                "AND NOT (a.action = ANY($2::text[]))",
                reader.org_unit, list(RULE_AUDIT_ACTIONS), cases,
            )  # fmt: skip
        return {r["principal_id"] for r in rows}

    async def model_writers(self) -> set[str]:
        async with self._pool.acquire() as conn:
            if await conn.fetchval("SELECT to_regclass('model_admin_audit')") is None:
                return set()
            return {r["by"] for r in await conn.fetch("SELECT DISTINCT by FROM model_admin_audit")}

    async def model_history(
        self, filters: StreamFilters, *, offset: int, limit: int
    ) -> tuple[list[AuditSectionEntry], int]:
        """The engines' history, newest first, paged here with its true total (rule 2)."""
        async with self._pool.acquire() as conn:
            if await conn.fetchval("SELECT to_regclass('model_admin_audit')") is None:
                return [], 0
            where = (
                "FROM model_admin_audit WHERE ($1::text[] IS NULL OR by = ANY($1::text[])) "
                "AND ($2::timestamptz IS NULL OR at >= $2) "
                "AND ($3::timestamptz IS NULL OR at < $3)"
            )
            args = [_ids(filters.who), filters.since, filters.until]
            total = await conn.fetchval(f"SELECT count(*) {where}", *args)
            rows = await conn.fetch(
                f"SELECT at, by, action, engine, changes, outcome {where} "
                "ORDER BY id DESC OFFSET $4 LIMIT $5",
                *args, offset, limit,
            )  # fmt: skip
        return [
            AuditSectionEntry(
                recorded_at=r["at"],
                who=r["by"],  # an id here: the route names it before serving (`name_entries`)
                action=r["action"],
                kind="models",
                held_in="models",
                detail={
                    "engine": r["engine"],
                    "changes": json.loads(r["changes"])
                    if isinstance(r["changes"], str)
                    else r["changes"],
                    "outcome": r["outcome"],
                },
            )
            for r in rows
        ], int(total or 0)


#: Said for an account the identity provider gives no name: never its id (rule 7, ADR-106 Am. 1).
NO_NAME = "An account with no name on record"
#: Said for a team's grant (`team:<role id>`), which is no account: never its role's id.
A_TEAM = "A team"


def _named(value: str, names: dict[str, str]) -> str:
    if value.startswith(TEAM_GRANT_PREFIX):
        return A_TEAM
    return names.get(value, NO_NAME)

#: The words of a shown entry that name a person, by action: each is served as that person's name,
#: never as the account's id. `user_id` and `account` name one wherever they are written.
_PERSON_KEYS = ("user_id", "account")
_PERSON_WORDS: dict[str, dict[str, str]] = {
    "set_team_lead": {"before": "one", "after": "one"},
    "set_team_cover": {"before": "first", "after": "first"},
    "change_dataset_owners": {"before": "many", "after": "many"},
    "make_home_case": {"owners": "many"},
    "transfer_owned_item": {"from": "one", "to": "one"},
}
#: The only other words a shown entry may carry. Anything else is left out, so an identifier a
#: later action writes (an identity provider's `subject`, a `username`, an `email`) is never served
#: by default: a new word is shown only once it is named here.
_PLAIN_WORDS = frozenset({
    "roles", "clearance", "org_unit", "receivable_handling_codes", "delivery", "transferred",
    "name", "version", "rights", "display_name", "mailbox", "level", "unit_level",
    "dataset_id", "member_ids", "source_id", "pack", "highest_marking", "kind", "id",
})
#: Never shown, though *Datasets* shows its words: a source's governance edit writes its handling,
#: its legal basis (free text) and what follows from them, which no Admin read serves
#: (`test_a_sources_governance_words_stay_withheld`).
_WITHHELD_WORDS = frozenset({
    "handling_before", "handling_after", "legal_basis_before", "legal_basis_after",
    "pipelines_needing_attention", "drafts_following",
})
#: Actions whose `before` and `after` are settings, not people.
_SETTING_CHANGES = frozenset({
    "change_custom_role", "set_dataset_egress", "set_dataset_promotion_policy",
    "set_dataset_owner_setting", "set_case_datasets",
})


def _person_values(action: str, key: str, value: Any) -> list[str]:
    shape = "one" if key in _PERSON_KEYS else _PERSON_WORDS.get(action, {}).get(key)
    if shape == "one":
        return [value] if isinstance(value, str) and value else []
    if shape == "first":
        return [value[0]] if isinstance(value, list) and value and isinstance(value[0], str) else []
    if shape == "many":
        return [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []
    return []


def people_in(action: str, detail: dict[str, Any]) -> set[str]:
    """The accounts a shown entry's words name, to be asked their names (ADR-106 decision 3)."""
    return {
        i for k, v in detail.items() for i in _person_values(action, k, v)
        if not i.startswith(TEAM_GRANT_PREFIX)
    }  # fmt: skip


def shown_words(action: str, detail: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """An entry's words as the Glass is served them: a person by name, the plain words named in
    `_PLAIN_WORDS` as they are, and nothing else."""
    out: dict[str, Any] = {}
    for key, value in detail.items():
        shape = "one" if key in _PERSON_KEYS else _PERSON_WORDS.get(action, {}).get(key)
        if shape is not None:
            label = "person" if key in _PERSON_KEYS else key
            if shape == "one":
                out[label] = _named(value, names) if isinstance(value, str) and value else None
            elif shape == "first":
                rest = value[1:] if isinstance(value, list) else []
                first = value[0] if isinstance(value, list) and value else None
                out[label] = [_named(first, names) if isinstance(first, str) and first else None,
                              *rest]  # fmt: skip
            else:
                out[label] = [_named(v, names) for v in value if isinstance(v, str) and v]
        elif key in _PLAIN_WORDS or (key in ("before", "after") and action in _SETTING_CHANGES):
            out[key] = value
    return out


def name_entries(
    entries: Sequence[AuditSectionEntry], names: dict[str, str]
) -> list[AuditSectionEntry]:
    """Entries whose `who` still holds an account id (the rule audit's, the engines') served by
    name instead."""
    return [e.model_copy(update={"who": names.get(e.who, NO_NAME)}) for e in entries]


def stream_entry(
    row: StreamRow, rights: frozenset[Right] | set[Right], names: dict[str, str]
) -> AuditSectionEntry:
    """One stream row as the reader is served it: who by name, its words and count only where
    `words_shown`, and those words with no account's id."""
    kind = kind_of(row.action)
    shown = words_shown(kind, rights)
    return AuditSectionEntry(
        recorded_at=row.recorded_at,
        who=names.get(row.principal_id, NO_NAME),
        action=row.action,
        kind=kind,
        held_in="case_and_admin",
        investigation_id=row.investigation_id,
        case_name=row.case_name,
        detail=shown_words(row.action, row.resolved_query, names) if shown else None,
        words_withheld=not shown,
        result_cardinality=row.result_cardinality if shown else None,
    )


def ids_to_name(rows: Sequence[StreamRow], rights: frozenset[Right] | set[Right]) -> set[str]:
    """Every account the page names: its writers, and the people its shown words name."""
    out = {r.principal_id for r in rows}
    for r in rows:
        if words_shown(kind_of(r.action), rights):
            out |= people_in(r.action, r.resolved_query)
    return out


def stream_entries(
    rows: Sequence[StreamRow], rights: frozenset[Right] | set[Right], names: dict[str, str]
) -> list[AuditSectionEntry]:
    return [stream_entry(r, rights, names) for r in rows]


def accounts_named(names: dict[str, str], name: str, among: set[str]) -> tuple[str, ...]:
    """The accounts, of those this reader may read, that a chosen name stands for (two people of
    one name are both kept: the picker offers names, so it cannot tell them apart)."""
    return tuple(sorted(i for i in among if names.get(i) == name))
