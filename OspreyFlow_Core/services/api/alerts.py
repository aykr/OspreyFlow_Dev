"""The alert store and disclosure mechanism — `06_DECISIONS.md` ADR-038/039, Phase 7 Stage 6a's own
foundation. Same shape `investigations.py`/`sites.py`/`pattern_store.py` already are: small,
relational, control-plane metadata, Postgres-backed rather than a fourth store — an alert is a
record of what fired, not graph content.

**The first store built since `tools/authorized_query_check.py` existed — `owner_id` is filtered
in the query itself from the start** (`06_DECISIONS.md` ADR-041), not written unscoped and fixed
later the way `sites.py`/`investigations.py`/`studio_recipes.py`/`pattern_store.py` each
independently were. `get_authorized` below has no Python-side ownership comparison anywhere in its
own body — `authorized-query-check` is what actually proves this, not this docstring's own claim
of it.

**References, not copies (`Alert.referent_node_ids`), access re-checked at read time
(`06_DECISIONS.md` ADR-039).** Two separate checks compose on every read: `get_authorized` proves
*ownership* (the SQL predicate above); `evidence_available` below proves the *referents* are still
visible to the reading principal right now, via the same `GraphPort.get_node` every other read
already goes through — ownership of the row and visibility of what it references are independent
facts, and neither is trusted to imply the other. A `NOTIFY_STUB` alert has no referent to
recheck by construction (`Alert.mode`'s own docstring) — `evidence_available` returns `True` for
one immediately, never calling `get_node` at all, not merely expected to return "nothing to hide"
if it did.

**The disclosure mechanism (`06_DECISIONS.md` ADR-038) is deliberately generic, not hotlist-
specific.** `record_match` takes an abstract "does `recipient` already see this referent" question
and a caller-supplied `matched_identifier` used only for the audit trail, never stored on the
`Alert` row — no `HotlistStore`/`MonitorStore` exists yet (Stage 6a's own "foundation only" scope:
no hotlist UI, no monitor scheduling), and none is needed for this mechanism to be real and
tested: a future hotlist evaluator and a future saved-pattern monitor both call this same function
once they exist, rather than each reimplementing the strict/notify switch and its audit
obligation independently.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

import asyncpg

from conduit_common.identity import new_id
from ports.graph import GraphPort
from schemas.domain import Alert, AlertMode, Interval, Principal

from .audit import AuditWriter
from .dataset_scope import reach_clause

DisclosurePolicy = Literal["strict", "notify"]

#: `06_DECISIONS.md` ADR-038's own binding requirement: "an unset, empty or unrecognised
#: configuration value means `strict`" — a whitelist match to exactly `"notify"`, defaulting to
#: `"strict"` for everything else, is fail-closed by construction rather than by a separate check.
_NOTIFY_VALUE = "notify"

#: `ADD COLUMN IF NOT EXISTS` below, not only in the `CREATE TABLE` itself — this codebase has no
#: migration tooling yet (`CLAUDE.md`: "No `osprey` CLI yet"), and `CREATE TABLE IF NOT EXISTS` is
#: a no-op against a database an earlier stage's own bootstrap already ran on, the persistent
#: `ospreyflow` database this whole build has shared across every session included. Without this,
#: `investigation_id` (Stage 6c) would exist for a fresh database and silently not exist for this
#: one, discovered only as a runtime `UndefinedColumnError` the first time a Stage 6c code path
#: actually read it.
_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    referent_node_ids TEXT NOT NULL,
    investigation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS investigation_id TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS dataset_id TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS typology TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS words TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS edge_ids TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS event_ids TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS window_json TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS trigger TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_node_id TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS assignee TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS disposition TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS disposition_reason TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS decided_by TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS alerts_investigation_idx ON alerts (investigation_id);
CREATE INDEX IF NOT EXISTS alerts_owner_id_idx ON alerts (owner_id);
"""


def disclosure_policy_from_value(raw: str | None) -> DisclosurePolicy:
    """`06_DECISIONS.md` ADR-038: deployment-level, read once, fails closed. Every value other
    than exactly `"notify"` — unset, empty, misspelled, or genuinely something else — resolves to
    `"strict"`; there is no second branch that could accidentally treat an unrecognised value as
    `"notify"`."""
    return "notify" if raw == _NOTIFY_VALUE else "strict"


class AlertNotFoundError(Exception):
    """Also raised when the alert exists but `owner_id` does not match the calling principal —
    the same existence-leak discipline `PatternNotFoundError`/`SiteNotFoundError` already
    establish."""


#: Every column an `Alert` is read from; one list, so a new column cannot be read by one query and
#: missed by another.
_COLUMNS = (
    "id, rule_id, owner_id, mode, referent_node_ids, investigation_id, created_at, dataset_id, "
    "typology, words, edge_ids, event_ids, window_json, trigger, alert_node_id, status, assignee, "
    "disposition, disposition_reason, decided_by, decided_at"
)


def _row_to_alert(row: asyncpg.Record) -> Alert:
    return Alert(
        id=row["id"],
        rule_id=row["rule_id"],
        owner_id=row["owner_id"],
        mode=AlertMode(row["mode"]),
        referent_node_ids=json.loads(row["referent_node_ids"]),
        investigation_id=row["investigation_id"],
        created_at=row["created_at"],
        dataset_id=row["dataset_id"],
        typology=row["typology"],
        words=row["words"],
        edge_ids=json.loads(row["edge_ids"]) if row["edge_ids"] else [],
        event_ids=json.loads(row["event_ids"]) if row["event_ids"] else [],
        window=Interval.model_validate_json(row["window_json"]) if row["window_json"] else None,
        trigger=row["trigger"],
        alert_node_id=row["alert_node_id"],
        status=row["status"],
        assignee=row["assignee"],
        disposition=row["disposition"],
        disposition_reason=row["disposition_reason"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
    )


class AlertStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> AlertStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # reasoning (the Stage 6c connection-ceiling finding).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def save(self, alert: Alert) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO alerts ({_COLUMNS}) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, "
                "$17, $18, $19, $20, $21)",
                alert.id,
                alert.rule_id,
                alert.owner_id,
                alert.mode.value,
                json.dumps(alert.referent_node_ids),
                alert.investigation_id,
                alert.created_at,
                alert.dataset_id,
                alert.typology,
                alert.words,
                json.dumps(alert.edge_ids),
                json.dumps(alert.event_ids),
                alert.window.model_dump_json() if alert.window else None,
                alert.trigger,
                alert.alert_node_id,
                alert.status,
                alert.assignee,
                alert.disposition,
                alert.disposition_reason,
                alert.decided_by,
                alert.decided_at,
            )

    async def get_authorized(self, alert_id: str, principal: Principal) -> Alert:
        """`owner_id` filtered in the query itself — `06_DECISIONS.md` ADR-041, proven (not
        merely claimed) by `tools/authorized_query_check.py`, which this store must pass on
        first write. This is the *ownership* check only; a caller reading evidence still needs
        `evidence_available` below for the *referent* recheck ADR-039 separately requires."""
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM alerts WHERE id = $1 AND owner_id = $2{reach}",
                alert_id,
                principal.id,
                *extra,
            )
        if row is None:
            raise AlertNotFoundError(alert_id)
        return _row_to_alert(row)

    async def list_authorized(self, principal: Principal) -> list[Alert]:
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM alerts WHERE owner_id = $1{reach} "
                "ORDER BY created_at DESC",
                principal.id,
                *extra,
            )
        return [_row_to_alert(row) for row in rows]

    async def list_case_queue(self, investigation_id: str, principal: Principal) -> list[Alert]:
        """ADR-109 ruling 3 — the case team's queue: every rule-raised alert of the case within
        the reader's dataset reach, newest first, whoever deployed the rule. Whether the reader may
        open the case is the route's level check; whether they may see each alert's evidence is
        the caller's (`evidence_available`, all-or-nothing), before anything is shown or counted."""
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM alerts WHERE investigation_id = $1 "
                f"AND typology IS NOT NULL{reach} ORDER BY created_at DESC",
                investigation_id,
                *extra,
            )
        return [_row_to_alert(row) for row in rows]

    async def get_case_alert(
        self, alert_id: str, investigation_id: str, principal: Principal
    ) -> Alert:
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM alerts WHERE id = $1 AND investigation_id = $2 "
                f"AND typology IS NOT NULL{reach}",
                alert_id,
                investigation_id,
                *extra,
            )
        if row is None:
            raise AlertNotFoundError(alert_id)
        return _row_to_alert(row)

    async def set_triage(
        self,
        alert_id: str,
        investigation_id: str,
        *,
        expect_status: Sequence[str],
        status: str,
        assignee: str | None,
        disposition: str | None = None,
        disposition_reason: str | None = None,
        decided_by: str | None = None,
        alert_node_id: str | None = None,
        edge_ids: Sequence[str] | None = None,
    ) -> Alert:
        """Moves one case alert from a status in `expect_status` to `status`, in one statement, so
        two members acting at once cannot both win (the loser is told it moved on). `alert_node_id`
        and `edge_ids`, when given, replace what the alert cites with the revisions triage wrote."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE alerts SET status = $3, assignee = $4, disposition = $5, "
                "disposition_reason = $6, decided_by = $7, "
                "decided_at = CASE WHEN $7::text IS NULL THEN NULL ELSE now() END, "
                "alert_node_id = COALESCE($8, alert_node_id), edge_ids = COALESCE($10, edge_ids) "
                "WHERE id = $1 AND investigation_id = $2 AND status = ANY($9::text[]) "
                f"RETURNING {_COLUMNS}",
                alert_id,
                investigation_id,
                status,
                assignee,
                disposition,
                disposition_reason,
                decided_by,
                alert_node_id,
                list(expect_status),
                None if edge_ids is None else json.dumps(list(edge_ids)),
            )
        if row is None:
            raise AlertTriageConflict(alert_id)
        return _row_to_alert(row)


    async def close_for_elements(
        self,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        *,
        closed_by: str,
        at: datetime,
        reason: str,
    ) -> int:
        """Closes every alert not already closed that is one of a reverted load's own (its `Alert`
        node is in `node_ids`) or that cites a node in `node_ids` or a link in `edge_ids`, so the
        queue names nothing that rests on a reverted element (ADR-127 Amendment 6). The queue's own
        read leaves out an alert whose cited node is hidden but checks no link, so one citing only a
        reverted link would stay listed. No disposition: it was neither confirmed nor dismissed by a
        member, it was taken back, and the reason says so. Not scoped to a reader or a case, as the
        revert removes its own elements. Idempotent: a closed alert is not touched again, so a
        second call returns 0. An alert citing a transaction the load wrote is not found by this,
        since an alert names events by id and the load's event ids are not in its record."""
        if not node_ids and not edge_ids:
            return 0
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE alerts SET status = 'closed', assignee = NULL, decided_by = $3, "
                "decided_at = $4, disposition_reason = $5 WHERE status <> 'closed' AND ("
                "alert_node_id = ANY($1::text[]) "
                "OR COALESCE(NULLIF(referent_node_ids, ''), '[]')::jsonb ?| $1::text[] "
                "OR COALESCE(NULLIF(edge_ids, ''), '[]')::jsonb ?| $2::text[]) RETURNING id",
                list(node_ids),
                list(edge_ids),
                closed_by,
                at,
                reason,
            )
        return len(rows)


    async def alerts_citing_events(self) -> dict[str, list[str]]:
        """The alerts not yet closed that name events (`event_ids` not empty), each with the ids it
        names, whoever may read them: for the revert, which closes the ones that cite an event it
        retracts (ADR-127 Amendment 8). Alerts are few, and an alert's event ids a handful, so the
        revert asks the events store about these ids, never for a load's events."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, event_ids FROM alerts WHERE status <> 'closed' "
                "AND event_ids IS NOT NULL AND event_ids NOT IN ('', '[]')"
            )
        return {row["id"]: json.loads(row["event_ids"]) for row in rows}

    async def close_by_ids(
        self, alert_ids: Sequence[str], *, closed_by: str, at: datetime, reason: str
    ) -> int:
        """Closes these alerts if they are not closed already, with no disposition (taken back, not
        decided by a member), and returns how many it closed: a second call returns 0."""
        if not alert_ids:
            return 0
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE alerts SET status = 'closed', assignee = NULL, decided_by = $2, "
                "decided_at = $3, disposition_reason = $4 "
                "WHERE id = ANY($1::text[]) AND status <> 'closed' RETURNING id",
                list(alert_ids),
                closed_by,
                at,
                reason,
            )
        return len(rows)


class AlertTriageConflict(Exception):
    """The alert was not in a state that allows this (someone else claimed or closed it)."""


async def evidence_available(alert: Alert, principal: Principal, graph: GraphPort) -> bool:
    """The read-time referent recheck `06_DECISIONS.md` ADR-039 requires — never trusted from
    write time. `NOTIFY_STUB` alerts have nothing to recheck (`Alert.mode`'s own docstring: no
    referent is ever stored for one) and are always "available" in this narrow sense, since there
    is no evidence to become unavailable. A `FULL` alert's evidence is available only if *every*
    referenced node is still visible to `principal` right now — one hidden referent is enough to
    withdraw the whole alert's evidence, the same all-or-nothing shape `_project`
    (`working_set/service.py`) already gives an edge whose endpoint is hidden."""
    if alert.mode is AlertMode.NOTIFY_STUB:
        return True
    for node_id in alert.referent_node_ids:
        if await graph.get_node(node_id, principal) is None:
            return False
    return True


async def record_match(
    *,
    graph: GraphPort,
    alert_store: AlertStore,
    audit: AuditWriter,
    recipient: Principal,
    rule_id: str,
    matched_identifier: str,
    triggering_node_ids: list[str],
    policy: DisclosurePolicy,
    investigation_id: str | None = None,
    dataset_id: str | None = None,
) -> Alert | None:
    """The disclosure mechanism itself — `06_DECISIONS.md` ADR-038. `triggering_node_ids` is
    whatever node(s) the match is actually about (a hotlisted identifier's own node, a saved
    pattern's own matched nodes); `matched_identifier` is a human-readable label used only for the
    audit trail below, never stored on the `Alert` row itself, not even for a `notify` stub —
    ADR-038's own decision text is explicit that `notify` "carries no referent of any kind",
    tighter than its own first draft, which would have allowed exactly this identifier through.
    `investigation_id` (Stage 6c, `schemas.domain.Alert.investigation_id`'s own docstring) is
    dropped for a `notify` stub for the identical reason `matched_identifier` already is — it is
    information about the triggering event, from the *ingesting* analyst's own context, and ADR-038
    draws no exception for it in "carries no referent of any kind" just because it isn't a node id.

    Returns the written `Alert` when one is written (always, under `full` visibility or `notify`),
    `None` under `strict` when the match is outside `recipient`'s own access — `strict`'s whole
    point is that no alert row exists at all in that case, not a row the recipient merely cannot
    open (`06_DECISIONS.md` ADR-038's option (a), as decided)."""
    visible = True
    for node_id in triggering_node_ids:
        if await graph.get_node(node_id, recipient) is None:
            visible = False
            break

    if visible:
        alert = Alert(
            id=new_id(),
            rule_id=rule_id,
            owner_id=recipient.id,
            mode=AlertMode.FULL,
            referent_node_ids=triggering_node_ids,
            investigation_id=investigation_id,
            created_at=datetime.now(UTC),
            dataset_id=dataset_id,
        )
        await alert_store.save(alert)
        return alert

    # Out of the recipient's own access — audited in both modes, `06_DECISIONS.md` ADR-038's own
    # binding requirement: "Audited in both modes... the record a customer's security function
    # would need to be shown what the system did on their behalf, in either mode, including the
    # mode that produces no visible alert at all."
    await audit.record(
        principal=recipient,
        action="hotlist_match_suppressed" if policy == "strict" else "hotlist_match_notified",
        resolved_query={"identifier": matched_identifier, "mode": policy},
        result_cardinality=0 if policy == "strict" else 1,
    )

    if policy == "strict":
        return None

    stub = Alert(
        id=new_id(),
        rule_id=rule_id,
        owner_id=recipient.id,
        mode=AlertMode.NOTIFY_STUB,
        referent_node_ids=[],
        created_at=datetime.now(UTC),
        dataset_id=dataset_id,
    )
    await alert_store.save(stub)
    return stub


__all__ = [
    "AlertNotFoundError",
    "AlertStore",
    "AlertTriageConflict",
    "DisclosurePolicy",
    "disclosure_policy_from_value",
    "evidence_available",
    "record_match",
]
