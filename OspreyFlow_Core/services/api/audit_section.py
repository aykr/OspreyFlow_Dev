"""Admin › Audit (`06_DECISIONS.md` ADR-145 decision 10, O2; Amendment 3 decision 1; ADR-112
Amendment 7 decision 7; ADR-146 Amendment 2: the rule audit returns here for the Administrator).

One view over the records that already exist, read under the reader's own principal (rule 3):

- **The audit stream** (`audit_log`, written by `AuditWriter.record` on every route): the case
  audit, the people, roles and dataset audits, and the loads. An entry is the reader's unit's when
  the case it names is owned by that unit, or, naming no case, when it was written by an account of
  that unit (`audit_log.org_unit`, from L2.6). **The unit filter is in the `WHERE` clause**
  (rule 3),
  so another unit's entry is neither on the page nor in the total; a filter is only ever ANDed after
  it, so a filter never widens the read. An entry naming a case that does not exist, or written
  before `org_unit` and naming no case, belongs to no unit and is never shown (fail closed).
- **The rule audit** (ADR-109 ruling 1) is never read here from the stream: its entries carry words
  (a firing's) that `rule_holds.readable_rule_audit` withholds entry by entry as the reader. They
  are
  left out of the stream's read entirely, and the `rules` record is served by that read itself, for
  one case, behind the gate the case's own rule-audit route uses (`app.py`).
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
from datetime import datetime
from typing import Any

import asyncpg

from schemas.admin import AuditKind, AuditSectionEntry
from schemas.domain import Principal
from schemas.rights import Right

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
    ),
    "loads_and_promotions": (
        "run_studio_recipe",
        "run_schedule_now",
        "publish_studio_recipe",
        "verify_studio_recipe",
        "upload_ingest_source_file",
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
        "set_promotion_alert_days",
        "load_reverted",
        "resume_recipe_schedule",
        "resume_source_refresh",
        "create_studio_recipe_version",
    ),
    "types": (
        "link_type_propose",
        "link_type_promote",
        "link_type_reject",
        "link_type_withdraw",
        "link_type_retire",
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
    ),
}
_CLASSIFIED: tuple[str, ...] = tuple(a for actions in KIND_ACTIONS.values() for a in actions)

#: The kinds whose words the reader's own section shows them, and the right that section needs.
WORDS_SHOWN_WITH: dict[str, Right] = {
    "people_and_roles": Right.MANAGE_PEOPLE,
    "datasets": Right.ADMINISTER_SYSTEM,
}

STREAM_KINDS = (*KIND_ACTIONS, "reads_and_other")

#: Said with every page of the stream, so nothing left out is left out silently (rule 2).
STREAM_NOTE = (
    "Entries about another unit's cases are not shown. An entry that names no case is shown by "
    "the unit of the account that wrote it: one written before 8 November 2026, or by the system "
    "itself (a reverted load, a map prefetch), recorded no unit of yours and is not shown. "
    "The rule audit is read for one case at a time: choose Rule audit of one case."
)
#: Said instead to a reader of `read_audit` who is not the unit's administrator: ADR-052 §4 lets
#: only `osprey-admin` see the unit's cases without a level on them, so no case's entry is sent.
STREAM_NOTE_NO_CASES = (
    "You hold read_audit but are not your unit's administrator, so entries about cases are not "
    "shown to you: only entries that name no case, written by your unit's accounts. An entry that "
    "names no case and recorded no unit (written before 8 November 2026, or by the system) is not "
    "shown either."
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

    who: str | None = None
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
            "AND ($3::text IS NULL OR a.principal_id = $3) "
            "AND ($4::text IS NULL OR a.investigation_id = $4) "
            "AND ($5::text IS NULL OR (a.action = ANY($9::text[]) AND ("
            "    a.resolved_query->>'dataset_id' = $5 "
            "    OR coalesce(a.resolved_query->'dataset_ids', '[]'::jsonb) ? $5))) "
            "AND ($6::timestamptz IS NULL OR a.recorded_at >= $6) "
            "AND ($7::timestamptz IS NULL OR a.recorded_at < $7)"
        )
        args: list[Any] = [
            reader.org_unit, list(RULE_AUDIT_ACTIONS), filters.who, filters.investigation_id,
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

    async def model_history(
        self, filters: StreamFilters, *, offset: int, limit: int
    ) -> tuple[list[AuditSectionEntry], int]:
        """The engines' history, newest first, paged here with its true total (rule 2)."""
        async with self._pool.acquire() as conn:
            if await conn.fetchval("SELECT to_regclass('model_admin_audit')") is None:
                return [], 0
            where = (
                "FROM model_admin_audit WHERE ($1::text IS NULL OR by = $1) "
                "AND ($2::timestamptz IS NULL OR at >= $2) "
                "AND ($3::timestamptz IS NULL OR at < $3)"
            )
            args = [filters.who, filters.since, filters.until]
            total = await conn.fetchval(f"SELECT count(*) {where}", *args)
            rows = await conn.fetch(
                f"SELECT at, by, action, engine, changes, outcome {where} "
                "ORDER BY id DESC OFFSET $4 LIMIT $5",
                *args, offset, limit,
            )  # fmt: skip
        return [
            AuditSectionEntry(
                recorded_at=r["at"],
                principal_id=r["by"],
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


def stream_entry(row: StreamRow, rights: frozenset[Right] | set[Right]) -> AuditSectionEntry:
    """One stream row as the reader is served it: its words and count only where `words_shown`."""
    kind = kind_of(row.action)
    shown = words_shown(kind, rights)
    return AuditSectionEntry(
        recorded_at=row.recorded_at,
        principal_id=row.principal_id,
        action=row.action,
        kind=kind,
        held_in="case_and_admin",
        investigation_id=row.investigation_id,
        case_name=row.case_name,
        detail=row.resolved_query if shown else None,
        words_withheld=not shown,
        result_cardinality=row.result_cardinality if shown else None,
    )


def stream_entries(
    rows: Sequence[StreamRow], rights: frozenset[Right] | set[Right]
) -> list[AuditSectionEntry]:
    return [stream_entry(r, rights) for r in rows]
