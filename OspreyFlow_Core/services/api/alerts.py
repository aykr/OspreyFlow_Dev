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
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Literal

import asyncpg

from conduit_common.identity import new_id
from ports.graph import GraphPort
from schemas.analytics import HOTLISTS_RULE, MONITORS_RULE, AlertFact
from schemas.domain import (
    Alert,
    AlertAudience,
    AlertKind,
    AlertMode,
    AlertSeverity,
    Handling,
    Interval,
    Principal,
)

from .audit import AuditWriter
from .dataset_scope import reach_clause
from .hotlists import BOOTSTRAP_SQL as _HOTLISTS_BOOTSTRAP_SQL

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
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS severity TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS team TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS handlings TEXT;
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
    "disposition, disposition_reason, decided_by, decided_at, severity, team"
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
        severity=row["severity"],
        team=row["team"],
    )


#: ADR-133 stage (a): the severity an alert has when nothing set one — every alert raised before
#: severity existed, and every producer that sets none. A hotlist names an exact identifier its
#: owner asked to be told about at once (ADR-038): high. A screening match (sanctions, PEPs) is
#: high; a shared contact detail, a weak signal alone, low; every other typology and a monitor's
#: match, medium. Read in the query (`_SEVERITY_SQL`), so no stored row is rewritten, and a filter
#: on severity is applied in the query too.
DEFAULT_SEVERITY: dict[AlertKind, AlertSeverity] = {
    "typology": "medium",
    "hotlist": "high",
    "monitor": "medium",
}
TYPOLOGY_SEVERITY: dict[str, AlertSeverity] = {
    "kyc_screening": "high",
    "shared_attributes": "low",
}


def default_severity(kind: AlertKind, typology: str | None) -> AlertSeverity:
    if kind == "typology" and typology in TYPOLOGY_SEVERITY:
        return TYPOLOGY_SEVERITY[typology]
    return DEFAULT_SEVERITY[kind]


def _quoted(value: str) -> str:
    # Only the constants above are ever quoted here, never a request's value.
    assert value.replace("_", "").isalnum(), value
    return f"'{value}'"


#: Which kind an alert is, from its row: a typology alert carries its typology; the others are told
#: apart by `rule_id`'s prefix. Anything else (a scheduled run's notice) is no kind, never queued.
_KIND_SQL = (
    "(CASE WHEN typology IS NOT NULL THEN 'typology' "
    "WHEN rule_id LIKE 'hotlist:%' THEN 'hotlist' "
    "WHEN rule_id LIKE 'monitor:%' THEN 'monitor' END)"
)
_SEVERITY_SQL = (
    "COALESCE(severity, CASE "
    + "".join(
        f"WHEN typology = {_quoted(t)} THEN {_quoted(v)} " for t, v in TYPOLOGY_SEVERITY.items()
    )
    + f"WHEN typology IS NOT NULL THEN {_quoted(DEFAULT_SEVERITY['typology'])} "
    + f"WHEN rule_id LIKE 'hotlist:%' THEN {_quoted(DEFAULT_SEVERITY['hotlist'])} "
    + f"ELSE {_quoted(DEFAULT_SEVERITY['monitor'])} END)"
)
_SEVERITY_RANK_SQL = (
    f"(CASE {_SEVERITY_SQL} WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END)"
)
#: Whether a hotlist or monitor alert is shared with its owner's team: a full alert (never a
#: `notify` stub, which carries nothing a second person may read; ADR-038) with a team written on
#: it, and — for a hotlist — whose hotlist's audience is `team` *now*, so an owner who turns a
#: hotlist back to "only me" takes its alerts back from the team too (ADR-133 ruling 3).
_SHARED_SQL = (
    "(mode = 'full' AND team IS NOT NULL AND (rule_id LIKE 'monitor:%' OR "
    "(rule_id LIKE 'hotlist:%' AND EXISTS (SELECT 1 FROM hotlists h "
    "WHERE h.id = substr(alerts.rule_id, 9) AND h.audience = 'team'))))"
)
_AUDIENCE_SQL = (
    f"(CASE WHEN typology IS NOT NULL THEN 'case' WHEN {_SHARED_SQL} THEN 'team' ELSE 'owner' END)"
)


def queue_scope(
    principal: Principal, investigation_id: str, position: int
) -> tuple[str, list[object]]:
    """ADR-133 decision 5, rule 3: which alerts the one queue may hold for `principal`, read in a
    case, as SQL (`AND (...)`, its parameters from `$position`). A typology alert is the case's
    members' (ADR-109 ruling 3); a hotlist or monitor alert is its owner's, and also their team's
    — the people of the owner's organisational unit — when it is shared (`_SHARED_SQL`). The
    dataset reach of the case applies to every kind (ADR-099 Amendment 3). Whether the reader may
    open the case is the route's level check; whether they may read what an alert names is the
    adapter's answer, read as them afterwards (`alert_queue.monitoring_queue`)."""
    case, me, unit = (f"${position + i}" for i in range(3))
    reach, extra = reach_clause(principal, position + 3)
    sql = (
        f" AND {_KIND_SQL} IS NOT NULL AND ("
        f"(typology IS NOT NULL AND investigation_id = {case}) "
        f"OR (typology IS NULL AND owner_id = {me}) "
        f"OR (typology IS NULL AND team = {unit} AND {_SHARED_SQL})){reach}"
    )
    return sql, [investigation_id, principal.id, principal.org_unit, *extra]


class QueueRow:
    """One alert as the queue's query read it: the alert, its kind, its severity (stored, else its
    kind's default) and who may see it."""

    __slots__ = ("alert", "audience", "kind", "severity")

    def __init__(
        self, alert: Alert, kind: AlertKind, severity: AlertSeverity, audience: AlertAudience
    ) -> None:
        self.alert = alert
        self.kind = kind
        self.severity = severity
        self.audience = audience


_QUEUE_COLUMNS = (
    f"{_COLUMNS}, {_KIND_SQL} AS kind, {_SEVERITY_SQL} AS severity_read, "
    f"{_AUDIENCE_SQL} AS audience"
)


def _row_to_queue_row(row: asyncpg.Record) -> QueueRow:
    return QueueRow(_row_to_alert(row), row["kind"], row["severity_read"], row["audience"])


_log = logging.getLogger(__name__)

#: ADR-134 decision 3: an alert as the analytics store keeps it for alert trends — its kind,
#: severity and audience read by the queue's own expressions, so the trend and the queue cannot
#: disagree about who an alert is for.
_FACT_COLUMNS = (
    f"id, rule_id, owner_id, investigation_id, created_at, dataset_id, typology, status, "
    f"disposition, team, handlings, {_KIND_SQL} AS kind, {_SEVERITY_SQL} AS severity_read, "
    f"{_AUDIENCE_SQL} AS audience"
)

FactSink = Callable[[list[AlertFact]], Awaitable[None]]


def _outcome(status: str, disposition: str | None) -> str:
    if status != "closed":
        return "claimed" if status == "claimed" else "open"
    return disposition if disposition in ("true_positive", "false_positive") else "closed"


def _row_to_fact(row: asyncpg.Record) -> AlertFact:
    kind = row["kind"]
    rule = (
        row["rule_id"]
        if kind == "typology"
        else HOTLISTS_RULE
        if kind == "hotlist"
        else MONITORS_RULE
    )
    raw = row["handlings"]
    return AlertFact(
        alert_id=row["id"],
        investigation_scope=row["investigation_id"],
        kind=kind,
        rule=rule,
        typology=row["typology"],
        severity=row["severity_read"],
        outcome=_outcome(row["status"], row["disposition"]),  # type: ignore[arg-type]
        raised_at=row["created_at"],
        owner_id=row["owner_id"],
        audience=row["audience"],
        team=row["team"],
        dataset_id=row["dataset_id"],
        handlings=None if raw is None else [Handling(**h) for h in json.loads(raw)],
    )


def distinct_handlings(handlings: Sequence[Handling]) -> list[Handling]:
    """Each handling once, in a stable order: what an alert rests on, not how often."""
    seen = {h.model_dump_json(): h for h in handlings}
    return [seen[k] for k in sorted(seen)]


class AlertStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        #: Where each written alert is kept for alert trends (ADR-134 decision 3): the analytics
        #: store's `load_alert_facts`, attached by `build_run_resources`. `None` keeps nothing.
        self.fact_sink: FactSink | None = None

    @classmethod
    async def connect(cls, dsn: str) -> AlertStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # reasoning (the Stage 6c connection-ceiling finding).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            # The queue's scope reads a hotlist's audience (`_SHARED_SQL`), so the table it reads
            # exists whichever store connects first — made by the hotlist store's own statement,
            # never a second copy of it.
            await conn.execute(_HOTLISTS_BOOTSTRAP_SQL)
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def publish_facts(self, alert_ids: Sequence[str]) -> None:
        """Keeps these alerts, as they now are, for alert trends. A failure is logged, not raised:
        the alert itself is written already, and `publish_all_facts` at the next start keeps it."""
        if self.fact_sink is None or not alert_ids:
            return
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_FACT_COLUMNS} FROM alerts WHERE id = ANY($1::text[]) "
                f"AND {_KIND_SQL} IS NOT NULL",
                list(alert_ids),
            )
        try:
            await self.fact_sink([_row_to_fact(r) for r in rows])
        except Exception:  # noqa: BLE001 — the queue row stands; the trend catches up at start
            _log.warning("alert facts not kept for %d alert(s)", len(rows), exc_info=True)

    async def publish_all_facts(self) -> int:
        """Every alert, kept again for alert trends: at each start, so the analytics store agrees
        with this one whatever happened while it was away. Alerts are few. Returns how many."""
        async with self._pool.acquire() as conn:
            ids = [r["id"] for r in await conn.fetch(f"SELECT id FROM alerts WHERE {_KIND_SQL} "
                                                       "IS NOT NULL")]  # fmt: skip
        for i in range(0, len(ids), 500):
            await self.publish_facts(ids[i : i + 500])
        return len(ids)

    async def publish_rule_facts(self, rule_id: str) -> None:
        """A rule's alerts kept again — a hotlist's, when its audience changes, so an owner who
        takes a hotlist back to "only me" takes its alerts back from the team's trends too."""
        async with self._pool.acquire() as conn:
            ids = [r["id"] for r in await conn.fetch("SELECT id FROM alerts WHERE rule_id = $1",
                                                       rule_id)]  # fmt: skip
        await self.publish_facts(ids)

    async def save(self, alert: Alert, *, handlings: Sequence[Handling] | None = None) -> None:
        """`handlings`: every handling the alert rests on, read as whoever raised it (ADR-134
        decision 3). Left out, they are not known, and alert trends count the alert for no one."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO alerts ({_COLUMNS}, handlings) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, "
                "$17, $18, $19, $20, $21, $22, $23, $24)",
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
                alert.severity,
                alert.team,
                None
                if handlings is None
                else json.dumps([h.model_dump() for h in distinct_handlings(handlings)]),
            )
        await self.publish_facts([alert.id])

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

    async def list_queue(
        self,
        investigation_id: str,
        principal: Principal,
        *,
        kinds: Sequence[str] | None = None,
        severities: Sequence[str] | None = None,
        statuses: Sequence[str] | None = None,
    ) -> list[QueueRow]:
        """ADR-133 decision 5: the one queue — every kind the reader may see (`queue_scope`), with
        the kind, severity and status filters applied in the query, most severe first, then the
        newest. Not cut: the queue is every alert the reader may see (rule 2)."""
        scope, extra = queue_scope(principal, investigation_id, 1)
        params: list[object] = list(extra)
        filters = ""
        for expression, wanted in (
            (_KIND_SQL, kinds),
            (_SEVERITY_SQL, severities),
            ("status", statuses),
        ):
            if wanted is not None:
                params.append(list(wanted))
                filters += f" AND {expression} = ANY(${len(params)}::text[])"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_QUEUE_COLUMNS} FROM alerts WHERE true{scope}{filters} "
                f"ORDER BY {_SEVERITY_RANK_SQL} DESC, created_at DESC, id",
                *params,
            )
        return [_row_to_queue_row(row) for row in rows]

    async def get_queue_alert(
        self, alert_id: str, investigation_id: str, principal: Principal
    ) -> QueueRow:
        """One alert of the queue, by the same scope as the list: an alert outside it is not found,
        whether it exists or not."""
        scope, extra = queue_scope(principal, investigation_id, 2)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_QUEUE_COLUMNS} FROM alerts WHERE id = $1{scope}", alert_id, *extra
            )
        if row is None:
            raise AlertNotFoundError(alert_id)
        return _row_to_queue_row(row)

    async def set_queue_triage(
        self,
        alert_id: str,
        investigation_id: str,
        principal: Principal,
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
        """`set_triage` for the one queue: the same single statement, and the alert must still be
        in the reader's queue scope as it is written, so a triage can reach no alert the queue
        would not show them."""
        scope, extra = queue_scope(principal, investigation_id, 10)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE alerts SET status = $2, assignee = $3, disposition = $4, "
                "disposition_reason = $5, decided_by = $6, "
                "decided_at = CASE WHEN $6::text IS NULL THEN NULL ELSE now() END, "
                "alert_node_id = COALESCE($7, alert_node_id), edge_ids = COALESCE($9, edge_ids) "
                f"WHERE id = $1 AND status = ANY($8::text[]){scope} "
                f"RETURNING {_COLUMNS}",
                alert_id,
                status,
                assignee,
                disposition,
                disposition_reason,
                decided_by,
                alert_node_id,
                list(expect_status),
                None if edge_ids is None else json.dumps(list(edge_ids)),
                *extra,
            )
        if row is None:
            raise AlertTriageConflict(alert_id)
        await self.publish_facts([alert_id])
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
        await self.publish_facts([alert_id])
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
        await self.publish_facts([r["id"] for r in rows])
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
        await self.publish_facts([r["id"] for r in rows])
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
    team: str | None = None,
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
    open (`06_DECISIONS.md` ADR-038's option (a), as decided).

    `team` (ADR-133 stage (a)) is the recipient's organisational unit, written on a full alert so
    the one queue can share it with that team when its rule allows (`queue_scope`); a `notify` stub
    never carries one."""
    visible = True
    rests_on: list[Handling] = []
    for node_id in triggering_node_ids:
        node = await graph.get_node(node_id, recipient)
        if node is None:
            visible = False
            break
        rests_on.append(node.handling)

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
            team=team,
        )
        await alert_store.save(alert, handlings=rests_on)
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
    # A stub cites nothing (ADR-038), so it rests on nothing: its owner's alone.
    await alert_store.save(stub, handlings=[])
    return stub


__all__ = [
    "DEFAULT_SEVERITY",
    "TYPOLOGY_SEVERITY",
    "AlertNotFoundError",
    "AlertStore",
    "AlertTriageConflict",
    "QueueRow",
    "default_severity",
    "distinct_handlings",
    "queue_scope",
    "DisclosurePolicy",
    "disclosure_policy_from_value",
    "evidence_available",
    "record_match",
]
