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

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

import asyncpg

from conduit_common.identity import new_id, new_node_id
from ontology.handling import HandlingScheme, load_uk_le_scheme, principal_may_view
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort, StoredLink
from schemas.analytics import (
    HOTLISTS_RULE,
    MONITORS_RULE,
    AlertFact,
    EventFilter,
    EventListRequest,
)
from schemas.domain import (
    CLOSING_REASONS,
    Alert,
    AlertAudience,
    AlertKind,
    AlertMode,
    AlertSeverity,
    Handling,
    Interval,
    Node,
    NodeWrite,
    Principal,
)

from .audit import AuditWriter
from .dataset_scope import reach_clause
from .hotlists import BOOTSTRAP_SQL as _HOTLISTS_BOOTSTRAP_SQL
from .hotlists import take_bootstrap_lock

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
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS close_proposed_by TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS close_proposed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS alerts_investigation_idx ON alerts (investigation_id);
CREATE INDEX IF NOT EXISTS alerts_owner_id_idx ON alerts (owner_id);
-- ADR-109 Amendment 10: a write that supersedes links (or an alert's node) alerts may cite keeps
-- one record here, from before the graph's commit until every citing alert cites the newest
-- revision the graph holds, its node is re-marked and renamed, and its working-set copies are
-- purged. Pairs are kept as written; what committed is read from the graph's stored states.
CREATE TABLE IF NOT EXISTS alert_repoint_records (
    id TEXT PRIMARY KEY,
    links JSONB NOT NULL DEFAULT '[]'::jsonb,
    alert_nodes JSONB NOT NULL DEFAULT '[]'::jsonb,
    purge JSONB NOT NULL DEFAULT '[]'::jsonb,
    applied BOOLEAN NOT NULL DEFAULT false,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alert_repoint_records_recorded_idx
    ON alert_repoint_records (recorded_at);
-- A settle's own re-mark pairs, kept apart from the write's (L2.8b's D1): one whose supersede never
-- landed is re-run, never waited on. A record held open by its writer across many transactions
-- (the re-marking script, D2) is settled by no one else while that writer is active.
ALTER TABLE alert_repoint_records
    ADD COLUMN IF NOT EXISTS remarks JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE alert_repoint_records
    ADD COLUMN IF NOT EXISTS held_open BOOLEAN NOT NULL DEFAULT false;
-- ADR-109 Amendment 12: each node a write corrects, which an alert may name among its
-- `referent_node_ids`, kept apart from `alert_nodes` (an alert's own node, whose old copies leave
-- every working set): a referent is renamed, never purged.
ALTER TABLE alert_repoint_records
    ADD COLUMN IF NOT EXISTS referents JSONB NOT NULL DEFAULT '[]'::jsonb;
"""


def disclosure_policy_from_value(raw: str | None) -> DisclosurePolicy:
    """`06_DECISIONS.md` ADR-038: deployment-level, read once, fails closed. Every value other
    than exactly `"notify"` — unset, empty, misspelled, or genuinely something else — resolves to
    `"strict"`; there is no second path that could accidentally treat an unrecognised value as
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
    "disposition, disposition_reason, decided_by, decided_at, severity, team, close_proposed_by, "
    "close_proposed_at"
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
        close_proposed_by=row["close_proposed_by"],
        close_proposed_at=row["close_proposed_at"],
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
    return disposition if disposition in CLOSING_REASONS else "closed"


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


#: The alerts citing any of `$1`'s links: an alert stores the links it cites as a JSON list.
_CITES_ANY_SQL = "COALESCE(NULLIF(edge_ids, ''), '[]')::jsonb ?| $1::text[]"


def _names_any_sql(param: int) -> str:
    """An alert naming any of the ids in parameter `$param` among its `referent_node_ids` (ADR-109
    Amendment 12)."""
    return f"COALESCE(NULLIF(referent_node_ids, ''), '[]')::jsonb ?| ${param}::text[]"


async def _lock_for_repoint(conn: asyncpg.Connection, old: Sequence[str]) -> None:
    """Every alert citing an old revision, locked in one statement in id order, so two repoints of
    the same link lock the same rows in the same order and never deadlock."""
    await conn.execute(
        f"SELECT id FROM alerts WHERE {_CITES_ANY_SQL} ORDER BY id FOR UPDATE", list(old)
    )


#: How long a recorded repoint may wait for its writer before a settle may drop it. A writer holds
#: it for one graph transaction, seconds; one still unsettled after this has lost its writer.
STALE_REPOINT_AFTER = timedelta(hours=1)

#: How often a record is marked live (`recorded_at` restarted) while its writer is still writing
#: (`LinkRepoint`, `OutsideCommitJournal`): the stale threshold then measures the time since its
#: writer was last
#: known alive, never the time since the record was opened, so a write open longer than
#: `STALE_REPOINT_AFTER` keeps its record (L2.8c review, item 3).
REPOINT_KEEP_ALIVE = timedelta(minutes=5)


class LinkRepoint:
    """One write's record (`AlertStore.repointing`): each superseded link, each superseded `Alert`
    node and each corrected node an alert may name (`superseded`), recorded and committed once the
    graph has returned the new id and before its commit. The record is opened at the first pair
    (ADR-109 Amendment 12, L2.8c's carry (f)), still before the commit, so a write that replaces
    nothing (an enrich stage that writes no point) opens none; `id` is `None` until then.
    `remarked_nodes`, once the record is applied: the alerts' nodes re-marked into revisions, which
    a caller holding the working sets purges (`purged` then closes the record). Callable as
    `GraphPort.supersede_node`'s `on_link_cloned`."""

    def __init__(self, store: AlertStore, *, held_open: bool = False) -> None:
        self._store = store
        self._held_open = held_open
        self.id: str | None = None
        self._alive: asyncio.Task[None] | None = None
        self.pairs: dict[str, str] = {}
        self.nodes: dict[str, str] = {}
        self.referents: dict[str, str] = {}
        self.remarked_nodes: list[str] = []
        #: Set by `never_committed`: the write was rolled back before its commit was sent.
        self.abandoned = False

    async def _record_id(self) -> str:
        """The record, opened at the first pair and kept live from then until its writer leaves
        (`AlertStore.keep_alive`)."""
        if self.id is None:
            self.id = await self._store.open_record(held_open=self._held_open)
            self._alive = self._store.keep_alive(self.id)
        return self.id

    async def _stop(self) -> None:
        if self._alive is not None:
            await self._store.stop_keeping_alive(self._alive)

    def never_committed(self) -> None:
        """Said by the writer as it rolls back a write whose commit it never sent (the graph
        refusing a confirm inside the close's transaction): nothing it recorded can land, so
        leaving the repointing closes the record. Never said once `commit_transaction` has been
        called, since a commit reported failed can still land (B3)."""
        self.abandoned = True

    async def record(self, old: str, new: str, *, old_type: str) -> None:
        """`old → new`, with the old link's own type (ADR-110 Amendment 18: two types may hold one
        id), so the settle reads that type's successor alone."""
        await self._store._add_to_record(await self._record_id(), links=[(old, new, old_type)])
        self.pairs[old] = new

    async def cloned(self, old: str, new: str, old_type: str) -> None:
        """`GraphPort.supersede_node`'s `on_link_cloned`: each link a node's correction clones,
        recorded as a link change's is (ADR-109 Amendment 11)."""
        await self.record(old, new, old_type=old_type)

    async def __call__(self, old: str, new: str, old_type: str) -> None:
        await self.cloned(old, new, old_type)

    async def superseded(self, old: str, new: str) -> None:
        """A node the write corrects (`supersede_node`'s returned id), recorded before the commit,
        so every alert naming `old` among its `referent_node_ids` is renamed to the node's newest
        revision once the write has committed (ADR-109 Amendment 12)."""
        await self._store._add_to_record(await self._record_id(), referents=[(old, new)])
        self.referents[old] = new

    async def record_node(self, old: str, new: str) -> None:
        await self._store._add_to_record(await self._record_id(), alert_nodes=[(old, new)])
        self.nodes[old] = new

    async def record_remark(self, old: str, new: str) -> None:
        """A re-mark's supersede of an alert's node (the re-marking script's), kept as a settle's
        own re-marks are: one that never landed is re-run by the settle, not waited on (D1)."""
        await self._store._add_to_record(await self._record_id(), remarks=[(old, new)])
        self.nodes[old] = new

    async def purged(self) -> None:
        """The caller has removed `remarked_nodes`' copies from every working set."""
        if self.id is not None:
            await self._store._close_record(self.id)


async def _repoint_cited_links(conn: asyncpg.Connection, repoint: Mapping[str, str]) -> list[str]:
    """Every alert citing an old revision in `repoint`, made to cite the new one: the rename map
    applied in SQL to each row as it now stands (locked by `_lock_for_repoint`), never a list read
    earlier and written back, which would undo a concurrent repoint. Returns the ids it changed."""
    rows = await conn.fetch(
        "UPDATE alerts SET edge_ids = (SELECT jsonb_agg(COALESCE($2::jsonb ->> t.e, t.e) "
        "ORDER BY t.n)::text FROM jsonb_array_elements_text(edge_ids::jsonb) "
        f"WITH ORDINALITY AS t(e, n)) WHERE {_CITES_ANY_SQL} RETURNING id",
        sorted(repoint),
        json.dumps(dict(repoint)),
    )
    return [r["id"] for r in rows]


def _loaded(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def _typed_pairs(raw: Any) -> list[tuple[str, str, str | None]]:
    """A record's link pairs, in order, each with its old link's type (`None` where none was
    recorded: the first hop is then read over every type)."""
    return [(str(p[0]), str(p[1]), str(p[2]) if len(p) > 2 else None) for p in _loaded(raw)]


def _pairs(raw: Any) -> list[tuple[str, str]]:
    """A record's pairs, in the order written."""
    return [(str(p[0]), str(p[1])) for p in _loaded(raw)]


#: The repoint records' advisory locks live in Postgres's two-key space under this first key,
#: never the one-key space every `pg_advisory_xact_lock(hashtext(...))` elsewhere in the Conduit
#: shares (`strength_influencers`, `target_models`, `studio_recipes`): a one-key lock and a two-key
#: lock never conflict, so no record's lock waits on, or is skipped for, another store's lock on
#: the same text (L2.8c, D10). The value is the ASCII of "ARPR"; `recipe_runs`' two-key locks
#: (`hashtext(recipe)`, `hashtext(case)`) meet it only should a recipe id hash to it, which makes
#: one settle skip a record a later read settles, as any collision here does.
REPOINT_LOCK_SPACE = 0x41525052

#: How long a settle waits for a connection from the lock pool before it refuses, in words
#: (`RepointLockBusy`), rather than waiting for ever (L2.8c, D10). A settle holds a lock connection
#: for one record's settle, seconds; one still waiting after this has met a stuck pool.
REPOINT_LOCK_WAIT = 30.0


class RepointLockBusy(Exception):
    """No connection came free in the repoint records' lock pool within `REPOINT_LOCK_WAIT`: the
    record is left, unsettled, for a later read (L2.8c, D10)."""


class RepointRecordGone(Exception):
    """A pair was to be recorded in a repoint record that is missing or already applied; the write
    it describes must not be committed, since nothing would apply it (ADR-109 Amendment 10, D2)."""


class AlertStore:
    def __init__(self, pool: asyncpg.Pool, lock_pool: asyncpg.Pool) -> None:
        self._pool = pool
        #: The repoint records' advisory locks are held on these connections, never the store's own
        #: pool: a settle holds its lock while its steps take connections from `_pool`, so locks
        #: drawn from `_pool` itself would let as many concurrent settles as it holds connections
        #: each wait for another, for ever (found when four reads settled at once). A settle waiting
        #: here holds nothing in `_pool`, so the two pools can never wait on each other.
        self._lock_pool = lock_pool
        #: `REPOINT_LOCK_WAIT`, `STALE_REPOINT_AFTER` and `REPOINT_KEEP_ALIVE`, per store so a test
        #: can shorten them.
        self.lock_wait = REPOINT_LOCK_WAIT
        self.stale_after = STALE_REPOINT_AFTER
        self.keep_alive_every = REPOINT_KEEP_ALIVE
        #: Where each written alert is kept for alert trends (ADR-134 decision 3): the analytics
        #: store's `load_alert_facts`, attached by `build_run_resources`. `None` keeps nothing.
        self.fact_sink: FactSink | None = None
        #: The deployment's handling scheme, for re-marking a repointed alert's node: the one
        #: `run_resources.build_run_resources` builds (`load_uk_le_scheme`), unless given.
        self.scheme: HandlingScheme = load_uk_le_scheme()

    @classmethod
    async def connect(cls, dsn: str) -> AlertStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # reasoning (the Stage 6c connection-ceiling finding).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        # Two at most, opened only when a record is settled (`_settle_record`).
        lock_pool = await asyncpg.create_pool(dsn=dsn, min_size=0, max_size=2)
        async with pool.acquire() as conn:
            # Each table's DDL in its own transaction, each under the start-up lock, so replicas
            # starting together take turns (ADR-109 Amendment 12). Never one transaction over both:
            # an `ALTER TABLE` takes its table's ACCESS EXCLUSIVE lock even when it changes nothing,
            # and one transaction holding the hotlists' while it waits for the alerts' inverts the
            # order the queue's reads take them in (alerts, then hotlists for `_SHARED_SQL`), so a
            # replica starting against live reads could deadlock with one (the L2.8d review's
            # item 4). The queue's scope reads a hotlist's audience (`_SHARED_SQL`), so the table
            # it reads exists whichever store connects first — made by the hotlist store's own
            # statement, never a second copy of it.
            for ddl in (_HOTLISTS_BOOTSTRAP_SQL, _BOOTSTRAP_SQL):
                async with conn.transaction():
                    await take_bootstrap_lock(conn)
                    await conn.execute(ddl)
        return cls(pool, lock_pool)

    async def close(self) -> None:
        await self._lock_pool.close()
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
                "$17, $18, $19, $20, $21, $22, $23, $24, $25, $26)",
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
                alert.close_proposed_by,
                alert.close_proposed_at,
                None
                if handlings is None
                else json.dumps([h.model_dump() for h in distinct_handlings(handlings)]),
            )
        await self.publish_facts([alert.id])

    async def with_alert_nodes(self, *, investigation_id: str | None = None) -> list[Alert]:
        """Every alert with an `Alert` node (of one case, if named), unscoped, for the operator's
        one-off re-marking (`scripts.remark_alert_nodes`): never returned to a reader."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM alerts WHERE alert_node_id IS NOT NULL "
                "AND ($1::text IS NULL OR investigation_id = $1) ORDER BY id",
                investigation_id,
            )
        return [_row_to_alert(r) for r in rows]

    async def handlings_of(self, alert_id: str) -> list[Handling] | None:
        """What the alert rests on, as its raiser read it (`save(handlings=)`), or `None` where not
        known."""
        async with self._pool.acquire() as conn:
            raw = await conn.fetchval("SELECT handlings FROM alerts WHERE id = $1", alert_id)
        return None if raw is None else [Handling(**h) for h in json.loads(raw)]

    async def handlings_by_id(self, alert_ids: Sequence[str]) -> dict[str, list[Handling] | None]:
        """`handlings_of` for many alerts in one query, fixed by the ids asked (rule 7)."""
        if not alert_ids:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, handlings FROM alerts WHERE id = ANY($1::text[])",
                sorted(set(alert_ids)),
            )
        return {
            r["id"]: None
            if r["handlings"] is None
            else [Handling(**h) for h in json.loads(r["handlings"])]
            for r in rows
        }

    async def set_alert_node(self, alert_id: str, node_id: str, *, was: str) -> bool:
        """The alert's `Alert` node is now `node_id`, a re-marked revision of `was`; only if it is
        still `was`, so a re-run, or a triage that confirmed the node in between, is not undone."""
        async with self._pool.acquire() as conn:
            done = await conn.fetchval(
                "UPDATE alerts SET alert_node_id = $2 WHERE id = $1 AND alert_node_id = $3 "
                "RETURNING id",
                alert_id,
                node_id,
                was,
            )
        return done is not None

    async def cited_by_ids(self, alert_ids: Sequence[str]) -> dict[str, Alert]:
        """The alerts with these ids, unscoped, for a check of what each cites, read as the reader
        by the caller (a pack's alert items, `packs.readable`): never returned to a reader."""
        if not alert_ids:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM alerts WHERE id = ANY($1::text[])", sorted(set(alert_ids))
            )
        return {r["id"]: _row_to_alert(r) for r in rows}

    async def get_authorized(
        self, alert_id: str, principal: Principal, *, graph: GraphPort | None = None
    ) -> Alert:
        """`owner_id` filtered in the query itself — `06_DECISIONS.md` ADR-041, proven (not
        merely claimed) by `tools/authorized_query_check.py`, which this store must pass on
        first write. This is the *ownership* check only; a caller reading evidence still needs
        `evidence_available` below for the *referent* recheck ADR-039 separately requires.
        Given the `graph`, pending repoints are settled first (`settle_pending`), as before every
        read of alerts whose evidence is then checked."""
        if graph is not None:
            await self.settle_pending(graph)
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

    async def list_authorized(
        self, principal: Principal, *, graph: GraphPort | None = None
    ) -> list[Alert]:
        """The principal's own alerts. Given the `graph`, pending repoints are settled first."""
        if graph is not None:
            await self.settle_pending(graph)
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

    async def case_of(self, alert_id: str) -> str | None:
        """The case an alert was raised in (`investigation_id`), or `None` for an id no alert holds
        or one raised in no case. Unscoped, so never answered to a reader: the address route
        (`open_alert_at_address`) checks the reader's level on it and reads the alert through the
        queue's own scope (`get_queue_alert`) before it says anything."""
        async with self._pool.acquire() as conn:
            found = await conn.fetchval(
                "SELECT investigation_id FROM alerts WHERE id = $1", alert_id
            )
        return found if isinstance(found, str) else None

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

    @asynccontextmanager
    async def repointing(
        self, graph: GraphPort, *, held_open: bool = False
    ) -> AsyncIterator[LinkRepoint]:
        """Around a write that supersedes links (or an `Alert` node) alerts may cite (ADR-109
        Amendments 9 and 10). The record is opened at the write's first pair (Amendment 12), before
        the commit; the caller records each `old → new` once the graph has returned it and before
        the commit, and a write that records nothing leaves no record. Left normally, the
        record is settled. Left by an exception (an `Exception`: a cancellation stays one, and its
        record waits for the next settle), it is settled too, applied if the graph shows the write
        committed, else left; the writer never drops a record holding a pair once it has sent the
        write's commit, since a commit can land after any check of it. Only the stale threshold
        drops one (`settle_pending`). A record is closed by its writer where its writer rolled
        back before sending its commit (`LinkRepoint.never_committed`). A settle failing on the
        exception path is logged, never raised in place of the write's own exception; the record
        waits.
        `held_open`, for a writer committing in many transactions (the re-marking script): no other
        settle applies the record while its writer is active (each pair it records keeps it so),
        since one applied part-way would miss the writer's later pairs (L2.8b's D2); a writer gone
        quiet for `STALE_REPOINT_AFTER` is taken to have crashed, and its record settled as any."""
        repoint = LinkRepoint(self, held_open=held_open)
        try:
            try:
                yield repoint
            finally:
                await repoint._stop()
        except Exception:
            if repoint.id is None:
                raise  # nothing recorded, so no record was opened (Amendment 12)
            record_id = repoint.id
            try:
                await self._release_record(record_id)
                if repoint.abandoned:
                    await self._close_record(record_id)
                else:
                    await self._settle_record(graph, record_id, writer=True)
            except Exception:  # noqa: BLE001 - the write's own exception is the one raised
                _log.exception("repoint record %s left for a later settle", record_id)
            raise
        if repoint.id is None:
            return
        record_id = repoint.id
        await self._release_record(record_id)
        try:
            repoint.remarked_nodes = await self._settle_record(graph, record_id, writer=True) or []
        except RepointLockBusy:
            # The write has committed and its record is released: a later read settles it (D10).
            _log.warning("repoint record %s left for a later settle", record_id, exc_info=True)

    def keep_alive(self, record_id: str) -> asyncio.Task[None]:
        """A task that marks the record live every `keep_alive_every` until it is applied or
        closed, or the task is cancelled (`stop_keeping_alive`) as its writer leaves. A writer
        that dies takes the task with it, so its record goes stale and, its write never
        committed, is dropped."""

        async def beat() -> None:
            while True:
                await asyncio.sleep(self.keep_alive_every.total_seconds())
                try:
                    async with self._pool.acquire() as conn:
                        done = await conn.execute(
                            "UPDATE alert_repoint_records SET recorded_at = now() "
                            "WHERE id = $1 AND NOT applied",
                            record_id,
                        )
                except Exception:  # noqa: BLE001 - a missed beat is retried at the next
                    _log.warning("repoint record %s not marked live", record_id, exc_info=True)
                    continue
                if done != "UPDATE 1":
                    return  # applied or closed: nothing left to keep

        return asyncio.create_task(beat())

    @staticmethod
    async def stop_keeping_alive(task: asyncio.Task[None]) -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def open_record(self, *, held_open: bool = False) -> str:
        """A new, empty repoint record; its id."""
        record_id = new_id()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO alert_repoint_records (id, held_open) VALUES ($1, $2)",
                record_id,
                held_open,
            )
        return record_id

    async def settle_pending(self, graph: GraphPort, *, now: datetime | None = None) -> None:
        """Before every read of alerts: every record whose write has committed is applied, so no
        reader is answered from an alert citing a superseded link or node. Run as a writer: the
        graph's unfiltered stored states (no reader, nothing returned), its own transactions, the
        id-ordered lock on the alerts and a lock on the record (a record another settle holds is
        skipped); it changes which revision an alert cites and the marking of its node, nothing a
        reader is answered beyond that. A record this read cannot settle is logged and left. A
        record older than `STALE_REPOINT_AFTER` none of whose links or nodes the graph shows
        superseded has lost its writer and is dropped. A record applied and waiting only for its
        working-set purge is left for the next working-set read (`purge_remarked_copies`)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, links, alert_nodes, referents, recorded_at, held_open "
                "FROM alert_repoint_records WHERE NOT applied"
            )
        cutoff = (now or datetime.now(UTC)) - self.stale_after
        for row in rows:
            if row["held_open"] and row["recorded_at"] >= cutoff:
                continue  # its writer is still recording (D2)
            try:
                done = await self._settle_record(graph, row["id"])
                if done is not None or row["recorded_at"] >= cutoff:
                    continue
                # Judged by the write's own pairs alone: a re-mark's (`remarks`) are the settle's.
                nodes = [*_pairs(row["alert_nodes"]), *_pairs(row["referents"])]
                superseded = [
                    state is not None and state.superseded
                    for state in [
                        await self._first_hop(graph, old, old_type)
                        for old, _, old_type in _typed_pairs(row["links"])
                    ]
                ]
                node_states = await graph.stored_writes([o for o, _ in nodes]) if nodes else {}
                superseded += [s.superseded for s in node_states.values()]
                if not any(superseded):
                    await self._close_record(row["id"])  # the write never happened
            except RepointLockBusy:
                # No lock connection came free: neither will one for the next record. The read
                # stops settling here, after one wait, rather than one wait per record (D10); every
                # record left waits for a later read.
                _log.warning("repoint records left for a later read", exc_info=True)
                break
            except Exception:  # noqa: BLE001 - one record never breaks a read: it waits
                # A record this read cannot settle (its links in no graph this deployment reads,
                # a store refusing for the moment) is left for a later settle or the stale
                # threshold; the read answers as the queue's check finds the alerts now.
                _log.warning("repoint record %s not settled", row["id"], exc_info=True)

    async def apply_repoints(self, finals: Mapping[str, str]) -> list[str]:
        """Every alert citing a link in `finals` made to cite the link it maps to, in one
        transaction: the rows locked together in id order, then renamed in SQL as they stand (never
        written back from a list read earlier). Returns the alerts changed."""
        if not finals:
            return []
        async with self._pool.acquire() as conn, conn.transaction():
            await _lock_for_repoint(conn, sorted(finals))
            moved = await _repoint_cited_links(conn, finals)
        await self.publish_facts(moved)
        return moved

    async def rename_alert_nodes(
        self, renamed: Mapping[str, str], *, referents: Mapping[str, str] | None = None
    ) -> tuple[list[str], list[str]]:
        """Every alert naming an old node in `renamed` or `referents`, as its own node or among its
        `referent_node_ids`, made to name the node it maps to, in one transaction, under the
        id-ordered lock `apply_repoints` takes: the rows locked together in id order first, so a
        rename and a repoint of the same alerts never take them in opposite orders and deadlock
        (L2.8c, D9). A referent pair renames an alert's own node too: a node a route corrects may
        be an alert's own `Alert` node (an editor confirming it from the canvas), and its alert
        must follow it as a referent's does (ADR-109 Amendment 12). A referent is renamed in SQL as
        the row stands, each id in place, never written back from a list read earlier. Returns the
        alerts whose referents were renamed, and the old nodes of `referents` that were an alert's
        own node (their copies are purged as an alert node's are)."""
        named = {**renamed, **(referents or {})}
        if not named:
            return [], []
        own: list[str] = []
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT id FROM alerts WHERE alert_node_id = ANY($1::text[]) "
                f"OR {_names_any_sql(2)} ORDER BY id FOR UPDATE",
                sorted(named),
                sorted(named),
            )
            for old, newest in named.items():
                done = await conn.execute(
                    "UPDATE alerts SET alert_node_id = $2 WHERE alert_node_id = $1", old, newest
                )
                if old not in renamed and done != "UPDATE 0":
                    own.append(old)
            rows = await conn.fetch(
                "UPDATE alerts SET referent_node_ids = (SELECT jsonb_agg(COALESCE("
                "$1::jsonb ->> t.e, t.e) ORDER BY t.n)::text "
                "FROM jsonb_array_elements_text(referent_node_ids::jsonb) "
                f"WITH ORDINALITY AS t(e, n)) WHERE {_names_any_sql(2)} RETURNING id",
                json.dumps(named),
                sorted(named),
            )
        moved = [r["id"] for r in rows]
        await self.publish_facts(moved)
        return moved, sorted(own)

    async def _add_to_record(
        self,
        record_id: str,
        *,
        links: Sequence[tuple[str, ...]] = (),
        alert_nodes: Sequence[tuple[str, str]] = (),
        remarks: Sequence[tuple[str, str]] = (),
        referents: Sequence[tuple[str, str]] = (),
    ) -> None:
        """Pairs appended to a record, in order, and committed at once, always before the graph
        commit they describe; a held-open record's clock restarts. Refused
        (`RepointRecordGone`), nothing written, where the record is missing or already applied:
        a pair recorded there would never be applied, so its writer must not commit (D2)."""
        async with self._pool.acquire() as conn:
            done = await conn.execute(
                "UPDATE alert_repoint_records SET links = links || $2::jsonb, "
                "alert_nodes = alert_nodes || $3::jsonb, remarks = remarks || $4::jsonb, "
                "referents = referents || $5::jsonb, "
                "recorded_at = CASE WHEN held_open THEN now() ELSE recorded_at END "
                "WHERE id = $1 AND NOT applied",
                record_id,
                json.dumps([list(p) for p in links]),
                json.dumps([list(p) for p in alert_nodes]),
                json.dumps([list(p) for p in remarks]),
                json.dumps([list(p) for p in referents]),
            )
        if done != "UPDATE 1":
            raise RepointRecordGone(record_id)

    async def _release_record(self, record_id: str) -> None:
        """Its writer has left: the record may be settled by anyone."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE alert_repoint_records SET held_open = false WHERE id = $1", record_id
            )

    @staticmethod
    async def _first_hop(graph: GraphPort, old: str, old_type: str | None) -> StoredLink | None:
        """The recorded link's own stored state, read for its recorded type alone (two types may
        hold one id, ADR-110 Amendment 18), or over every type where none was recorded."""
        return (await graph.stored_link_states([old], edge_type=old_type)).get(old)

    async def applied_purges(self) -> list[tuple[str, list[str]]]:
        """Each applied record still waiting for its working-set purge, with the nodes to purge."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, purge FROM alert_repoint_records WHERE applied AND purge <> '[]'::jsonb"
            )
        return [(row["id"], [str(n) for n in _loaded(row["purge"])]) for row in rows]

    async def purged(self, record_id: str) -> None:
        """The record's nodes have left every working set: the record is closed."""
        await self._close_record(record_id)

    async def _close_record(self, record_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM alert_repoint_records WHERE id = $1", record_id)

    @staticmethod
    async def _newest(
        read: Callable[[list[str]], Awaitable[Mapping[str, Any]]], start: str
    ) -> str | None:
        """The newest revision of `start` as the graph holds it, following each element's own
        `superseded_by` (the graph's stored state, its one truth of what committed); `None` where
        an element in the chain is not stored."""
        seen: set[str] = set()
        current = start
        while current not in seen:
            seen.add(current)
            state = (await read([current])).get(current)
            if state is None:
                return None
            if not state.superseded:
                return current
            if state.superseded_by is None:
                return None
            current = state.superseded_by
        return None

    async def _settle_record(
        self, graph: GraphPort, record_id: str, *, writer: bool = False
    ) -> list[str] | None:
        """One record applied if its write committed, under a lock on the record (a settle another
        process holds is skipped: `None`), every step idempotent so a failure part-way is retried:
        each recorded link's and node's newest revision read from the graph; the citing alerts
        moved to it; the alerts naming a recorded node renamed to its newest; the moved alerts'
        nodes re-marked (each supersede recorded first); then the record marked applied with the
        nodes to purge. Returns those nodes; `None` while the write has not committed."""
        # A session-level advisory lock, held on a `_lock_pool` connection across the whole settle
        # and released in `finally`; should the release fail, that connection is closed, not
        # returned to the pool holding it, and the server frees a session lock when its connection
        # ends, so a crashed settle never holds one for good. `hashtext` can map two ids to one key:
        # harmless, since a collision only makes a reader skip a record, which a later read settles.
        # The wait for a lock connection is bounded (`REPOINT_LOCK_WAIT`, D10): past it the settle
        # refuses in words and the record waits for a later read.
        try:
            lock = await self._lock_pool.acquire(timeout=self.lock_wait)
        except TimeoutError as waited:
            raise RepointLockBusy(
                f"repoint record {record_id} not settled: no lock connection came free within "
                f"{self.lock_wait:g} seconds; it is left for a later read"
            ) from waited
        try:
            if not await lock.fetchval(
                "SELECT pg_try_advisory_lock($1, hashtext($2))", REPOINT_LOCK_SPACE, record_id
            ):
                return None
            try:
                return await self._settle_held(graph, record_id, writer=writer)
            finally:
                try:
                    await lock.execute(
                        "SELECT pg_advisory_unlock($1, hashtext($2))", REPOINT_LOCK_SPACE, record_id
                    )
                except Exception:  # noqa: BLE001 - the lock must not outlive this settle
                    await lock.close()
        finally:
            await self._lock_pool.release(lock)

    async def _settle_held(
        self, graph: GraphPort, record_id: str, *, writer: bool
    ) -> list[str] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT links, alert_nodes, remarks, referents, purge, applied "
                "FROM alert_repoint_records WHERE id = $1",
                record_id,
            )
        if row is None:
            return []
        if row["applied"]:
            return list(_loaded(row["purge"]))
        links, nodes = _pairs(row["links"]), _pairs(row["alert_nodes"])
        referents = _pairs(row["referents"])
        if not links and not nodes and not referents and not _pairs(row["remarks"]):
            # Nothing recorded yet: a writer between opening its record and recording its first
            # pair. Only that writer closes it (it recorded nothing); a settle leaves it alone.
            if writer:
                await self._close_record(record_id)
                return []
            return None
        finals: dict[str, str] = {}
        for old, _, old_type in _typed_pairs(row["links"]):
            first = await self._first_hop(graph, old, old_type)
            if first is None or not first.superseded or first.superseded_by is None:
                return None  # not committed (or never: the stale threshold)
            newest = await self._newest(graph.stored_link_states, first.superseded_by)
            if newest is None:
                return None
            # An id two types hold cannot say which type's link an alert cites (alerts name a
            # link by id): no alert is moved by it, each left as the queue's check finds it (D3).
            # Every later revision's id is minted fresh (`new_edge_id`), so only the first hop can
            # be shared.
            if (await graph.stored_link_states([old]))[old].held_by == 1:
                finals[old] = newest
        renamed: dict[str, str] = {}
        for old, _ in nodes:
            newest = await self._newest(graph.stored_writes, old)
            if newest is None or newest == old:
                return None
            renamed[old] = newest
        # Each node the write corrected, followed to its newest revision as the graph holds it
        # (Amendment 12): every alert naming it among its referents is renamed, so it stays
        # listed for a reader of the new revision and is still refused to one who may not read
        # it. Its copies are not purged: a corrected entity is no alert's own node.
        named: dict[str, str] = {}
        for old, _ in referents:
            newest = await self._newest(graph.stored_writes, old)
            if newest is None or newest == old:
                return None
            named[old] = newest
        # The settle's own re-marks (D1): one that landed renames its alerts as the write's pairs
        # do; one that never landed (its old node still live) is re-run below, never waited on.
        rerun: list[str] = []
        for old, _ in _pairs(row["remarks"]):
            newest = await self._newest(graph.stored_writes, old)
            if newest is None or newest == old:
                rerun.append(old)
            else:
                renamed[old] = newest
        await self.apply_repoints(finals)
        _, own = await self.rename_alert_nodes(renamed, referents=named)
        remarked = await self._remark_citing(
            graph,
            record_id,
            sorted(set(finals.values())),
            sorted(
                {
                    *renamed.values(),
                    *(named[old] for old in own),
                    *(old for old in rerun if old not in renamed),
                }
            ),
            sorted(set(named.values())),
        )
        # Every alert node renamed or re-marked here is superseded: its working-set copies are
        # stale. A corrected entity's are not purged (it is no alert's own node).
        purge = sorted({*renamed, *own, *remarked})
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE alert_repoint_records SET applied = true, purge = $2::jsonb WHERE id = $1",
                record_id,
                json.dumps(purge),
            )
        if not purge:
            await self._close_record(record_id)
        return purge

    async def _remark_citing(
        self,
        graph: GraphPort,
        record_id: str,
        links: Sequence[str],
        nodes: Sequence[str] = (),
        referents: Sequence[str] = (),
    ) -> list[str]:
        """The nodes of the alerts citing `links`, and of those now naming one of `nodes` (a node
        the record renamed: a close's confirm copies its node at the marking it had, which its
        alert's evidence may now be above), and of those naming one of `referents` (a corrected
        node, whose new revision may be marked above the alert's node: Amendment 12), re-marked to
        their evidence now (ADR-109 Amendment 10), each supersede recorded in the record before
        its commit; returns the old nodes re-marked, whose working-set copies are to be purged."""
        if not links and not nodes and not referents:
            return []
        async with self._pool.acquire() as conn:
            found = await conn.fetch(
                f"SELECT id FROM alerts WHERE {_CITES_ANY_SQL} OR alert_node_id = ANY($3::text[]) "
                f"OR {_names_any_sql(2)} ORDER BY id",
                list(links),
                list(referents),
                list(nodes),
            )
        rows = list((await self.cited_by_ids([r["id"] for r in found])).values())

        async def recorded(old: str, new: str) -> None:
            await self._add_to_record(record_id, remarks=[(old, new)])

        report = await remark_alerts(graph, self, self.scheme, rows, on_supersede=recorded)
        return report.superseded_nodes

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
        close_proposed_by: str | None = None,
    ) -> Alert:
        """`set_triage` for the one queue: the same single statement, and the alert must still be
        in the reader's queue scope as it is written, so a triage can reach no alert the queue
        would not show them. `close_proposed_by` (ADR-133 decision 7): who proposed closing a
        high-severity alert; kept, with when, while the same person stays named, and cleared with
        `None`."""
        scope, extra = queue_scope(principal, investigation_id, 10)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE alerts SET status = $2, assignee = $3, disposition = $4, "
                "disposition_reason = $5, decided_by = $6, "
                "decided_at = CASE WHEN $6::text IS NULL THEN NULL ELSE now() END, "
                "alert_node_id = COALESCE($7, alert_node_id), "
                "close_proposed_at = CASE WHEN $9::text IS NULL THEN NULL "
                "WHEN close_proposed_by IS NOT DISTINCT FROM $9::text THEN close_proposed_at "
                "ELSE now() END, close_proposed_by = $9 "
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
                close_proposed_by,
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
        queue names nothing that rests on a reverted element (ADR-127 Amendment 6). The queue's
        own read already leaves out an alert any of whose nodes, links or transactions is hidden or
        gone (ADR-146 decision 10, G2); closing it says so in the record as well. No disposition:
        it was neither confirmed nor dismissed by a member, it was taken back, and the reason says
        so. Not scoped to a reader or a case, as the
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


def raiser_floor(alert: Alert, handlings: Sequence[Handling] | None) -> list[Handling]:
    """The markings an alert's words are held at whatever its evidence is marked now: none (ADR-109
    Amendment 12 point 10, the owner's ruling (a), 8 November 2026). A correction that lowers a node
    an alert names, or a link it cites, is the authorising act: the alert follows it and is listed
    to the reader the lower marking admits, as Amendments 10 and 11 have a lowered link do. An alert
    with its own node is still guarded by that node, which a re-mark never lowers. The queue's
    reads (`raiser_read_admits`), the rule audit and a pack's alert item all read this one
    function, so they agree; the interim ruling (b), which held an alert with no node at what its
    raiser read (`save(handlings=)`), would be `[] if alert.alert_node_id is not None else
    list(handlings or [])` here."""
    return []


def raiser_read_admits(
    alert: Alert, handlings: Sequence[Handling] | None, reader: Principal, scheme: HandlingScheme
) -> bool:
    """`reader` may read every marking of the alert's `raiser_floor`. A marking the scheme cannot
    judge refuses this alert alone, never the whole read (`principal_may_view` raising)."""
    try:
        return all(principal_may_view(h, reader, scheme) for h in raiser_floor(alert, handlings))
    except Exception:  # noqa: BLE001 - one alert unjudgeable is that alert refused (rule 3)
        _log.warning("alert %s refused: a marking its raiser read cannot be judged", alert.id)
        return False


async def raiser_reads_admitting(
    store: AlertStore, alerts: Sequence[Alert], reader: Principal
) -> set[str]:
    """The ids of `alerts` that `raiser_read_admits` lets `reader` read, the handlings read in one
    query for every alert asked (rule 7: the read follows the ids, never what is hidden)."""
    handlings = await store.handlings_by_id([a.id for a in alerts if a.alert_node_id is None])
    return {
        a.id
        for a in alerts
        if raiser_read_admits(a, handlings.get(a.id), reader, store.scheme)
    }


class AlertTriageConflict(Exception):
    """The alert was not in a state that allows this (someone else claimed or closed it)."""


def evidence_node_ids(alert: Alert) -> list[str]:
    """The nodes an alert rests on: the entities it concerns and its own `Alert` node."""
    return [*alert.referent_node_ids, *([alert.alert_node_id] if alert.alert_node_id else [])]


#: How many transactions one request asks for: `EventListRequest.limit`'s ceiling, so each request
#: is answered in one page.
EVENT_CHUNK = 200


class ReadableEvidence:
    """What of a batch of alerts' evidence the reader may read, each kind the adapter's own answer
    (rule 3): the nodes as read, and the ids of the links and transactions that came back."""

    __slots__ = ("edge_ids", "event_ids", "nodes")

    def __init__(
        self, nodes: dict[str, Node], edge_ids: frozenset[str], event_ids: frozenset[str]
    ) -> None:
        self.nodes, self.edge_ids, self.event_ids = nodes, edge_ids, event_ids

    def covers(
        self, node_ids: Iterable[str], edge_ids: Iterable[str], event_ids: Iterable[str]
    ) -> bool:
        """Every one of these nodes, links and transactions is readable."""
        return (
            all(i in self.nodes for i in node_ids)
            and set(edge_ids) <= self.edge_ids
            and set(event_ids) <= self.event_ids
        )

    def whole(self, alert: Alert) -> bool:
        """ADR-039's all-or-nothing: every node, link and transaction the alert cites is
        readable."""
        return (
            all(i in self.nodes for i in evidence_node_ids(alert))
            and set(alert.edge_ids) <= self.edge_ids
            and set(alert.event_ids) <= self.event_ids
        )


async def read_evidence(
    alerts: Sequence[Alert],
    reader: Principal,
    graph: GraphPort,
    analytics: AnalyticsPort,
    *,
    scope: Callable[[Alert], str | None],
) -> ReadableEvidence:
    """Every node, link and transaction the alerts cite, read **once per kind, in one batch**, as
    the reader, through each adapter's own access step (`get_nodes`, `get_edges`, `list_events`;
    ADR-146 decision 10, gap map G2). The reads are fixed by the ids cited, never by what comes
    back: transactions are asked in chunks of `EVENT_CHUNK` cut from the ids, in each alert's
    `scope` (an alert with none has its transactions read as hidden), so neither the number nor the
    size of the reads can follow what the reader may not see (rule 7)."""
    by_scope: dict[str, set[str]] = {}
    for a in alerts:
        where = scope(a)
        if a.event_ids and where is not None:
            by_scope.setdefault(where, set()).update(a.event_ids)
    return await read_evidence_ids(
        reader,
        graph,
        analytics,
        node_ids={i for a in alerts for i in evidence_node_ids(a)},
        edge_ids={i for a in alerts for i in a.edge_ids},
        event_ids_by_scope=by_scope,
    )


async def read_evidence_ids(
    reader: Principal,
    graph: GraphPort,
    analytics: AnalyticsPort,
    *,
    node_ids: Iterable[str],
    edge_ids: Iterable[str],
    event_ids_by_scope: Mapping[str, Iterable[str]],
) -> ReadableEvidence:
    """`read_evidence` over bare ids, for a record that cites them without being an alert (a rule
    audit entry): one batched read per kind as the reader, transactions in chunks of `EVENT_CHUNK`
    cut from the ids, per case."""
    nodes_wanted = sorted(set(node_ids))
    edges_wanted = sorted(set(edge_ids))
    nodes = {n.id: n for n in await graph.get_nodes(nodes_wanted, reader)} if nodes_wanted else {}
    edges = (
        frozenset(e.id for e in await graph.get_edges(edges_wanted, reader))
        if edges_wanted
        else frozenset()
    )
    events: set[str] = set()
    for where in sorted(event_ids_by_scope):
        ids = sorted(set(event_ids_by_scope[where]))
        for start in range(0, len(ids), EVENT_CHUNK):
            chunk = ids[start : start + EVENT_CHUNK]
            page = await analytics.list_events(
                EventListRequest(
                    filter=EventFilter(investigation_scope=where, event_ids=chunk),
                    limit=EVENT_CHUNK,
                ),
                reader,
            )
            events.update(e.event_id for e in page.events if e.event_id in chunk)
    return ReadableEvidence(nodes, edges, frozenset(events))


class RemarkReport:
    """What a re-mark changed, or would change (`remark_alerts`). `remarked` is what a second run
    must report empty."""

    def __init__(self) -> None:
        self.remarked: list[str] = []
        self.unsafe: list[str] = []
        self.checked = 0
        #: The script's purge (`scripts.remark_alert_nodes`): working sets that lost a stale copy.
        self.cases_purged = 0
        #: The nodes re-marked into revisions: what a caller holding the working sets removes
        #: from every case that stores a copy (`WorkingSetService.remove_reverted`).
        self.superseded_nodes: list[str] = []


async def remark_alerts(
    graph: GraphPort,
    alerts: AlertStore,
    scheme: HandlingScheme,
    rows: Sequence[Alert],
    *,
    dry_run: bool = False,
    on_supersede: Callable[[str, str], Awaitable[None]] | None = None,
) -> RemarkReport:
    """Each alert's `Alert` node raised to the highest marking of what it rests on now, read as the
    service principal: its entities, the links it cites and both ends of each (a reader who may
    not read an end is not given the link, and a node's correction can raise an end above its link:
    ADR-109 Amendment 11), the transactions its raiser read (its stored handlings) and its own
    marking (never lowered). A node below it is superseded by a
    revision at that marking, and the alert pointed at the revision only if it still names the old
    one. No single safe marking (referents restricted to different units): listed, not changed.
    The script's run (`scripts.remark_alert_nodes`, the nodes written before `7fac778`) and every
    repoint (ADR-109 Amendment 10: an alert whose link was re-marked above its node) use it."""
    from services.resolve.trigger import service_principal

    from .rule_evaluation import alert_handling

    reader = service_principal(scheme)
    report = RemarkReport()
    for alert in rows:
        if alert.alert_node_id is None:
            continue
        node = await graph.get_node(alert.alert_node_id, reader)
        if node is None:
            continue  # taken back or superseded since: nothing to re-mark
        report.checked += 1
        referents = await graph.get_nodes(sorted(set(alert.referent_node_ids)), reader)
        links = await graph.get_edges(sorted(set(alert.edge_ids)), reader) if alert.edge_ids else []
        end_ids = sorted({end for e in links for end in (e.source, e.target)})
        ends = await graph.get_nodes(end_ids, reader) if end_ids else []
        unread = (
            len(referents) < len(set(alert.referent_node_ids))
            or len(links) < len(set(alert.edge_ids))
            or len(ends) < len(end_ids)
        )
        if unread:
            # Something it rests on cannot be read for its marking (gone, pending in the journal):
            # no safe marking, never one guessed from what is left (as `write_alert_node`).
            report.unsafe.append(alert.id)
            continue
        rests_on = [
            node.handling,
            *(n.handling for n in referents),
            *(e.handling for e in links),
            *(n.handling for n in ends),
            *(await alerts.handlings_of(alert.id) or []),
        ]
        required = alert_handling(scheme, rests_on)
        if required is None:
            report.unsafe.append(alert.id)
            continue
        if required == node.handling:
            continue
        report.remarked.append(alert.id)
        if dry_run:
            continue
        tx = await graph.begin_transaction()
        try:
            revision = await graph.supersede_node(
                node.id,
                NodeWrite(id=new_node_id(), type=node.type, properties=node.properties,
                          provenance=node.provenance, handling=required,
                          created_by="remark_alert_nodes", created_at=datetime.now(UTC),
                          datasets=node.datasets),  # fmt: skip
                tx,
            )
            if on_supersede is not None:
                # Recorded before the commit: a failure before `set_alert_node` is repaired by
                # the next settle, which renames the alert's node to the revision.
                await on_supersede(node.id, revision)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
        if not await alerts.set_alert_node(alert.id, revision, was=node.id):
            _log.warning("alert %s no longer names node %s; its revision %s is unused",
                         alert.id, node.id, revision)  # fmt: skip
        report.superseded_nodes.append(node.id)
    return report


class _NoRepoint:
    """Where no alert store is given (a service built for a test of its own), nothing to repoint."""

    pairs: dict[str, str] = {}
    nodes: dict[str, str] = {}
    remarked_nodes: list[str] = []

    async def record(self, old: str, new: str, *, old_type: str) -> None:
        return None

    async def record_node(self, old: str, new: str) -> None:
        return None

    def never_committed(self) -> None:
        return None

    async def purged(self) -> None:
        return None

    async def cloned(self, old: str, new: str, old_type: str) -> None:
        return None

    async def __call__(self, old: str, new: str, old_type: str) -> None:
        return None

    async def superseded(self, old: str, new: str) -> None:
        return None


class SupersedeJournal(Protocol):
    """What a writer superseding a node reports to (ADR-109 Amendments 11 and 12): callable as
    `GraphPort.supersede_node`'s `on_link_cloned` for each link it clones, and `superseded` with
    the node itself and its new revision, before the commit. `LinkRepoint` for a writer that
    commits its own transaction, `OutsideCommitJournal` for one whose transaction another
    commits."""

    async def __call__(self, old: str, new: str, old_type: str) -> None: ...

    async def superseded(self, old: str, new: str) -> None: ...


@asynccontextmanager
async def repointing_alerts(
    alerts: AlertStore | None, graph: GraphPort
) -> AsyncIterator[LinkRepoint | _NoRepoint]:
    """`AlertStore.repointing` for a service that supersedes links (ADR-109 Amendment 10): every
    `supersede_edge` of a link alerts may cite runs inside it, recording `old → new` before the
    graph's commit."""
    if alerts is None:
        yield _NoRepoint()
        return
    async with alerts.repointing(graph) as repoint:
        yield repoint


class OutsideCommitJournal:
    """The repoint journal for a writer whose graph transaction another commits (ADR-109 Amendment
    11): the job worker's `supersede_node` and resolution runs (`NOT_SAME_AS`), whose `tx` the
    worker commits after the handler returns. Each `old → new` is recorded, before that commit, in
    one record opened at the first pair (a write that replaces no link leaves none). The record is
    kept live while its writer writes (`AlertStore.keep_alive`, from the first pair until the
    writer leaves `journal_outside_commit`), so a write open longer than `STALE_REPOINT_AFTER`
    keeps it; once the writer leaves, its committer commits at once. Its writer never settles it,
    since the commit is not its own: the next read of alerts settles it once the graph's stored
    states show the write committed, as any record (`settle_pending`); one whose write never
    commits is dropped once stale. Called as `on_link_cloned`, or after a `supersede_edge`, with
    the old link's type."""

    def __init__(self, store: AlertStore) -> None:
        self._store = store
        self.record_id: str | None = None
        self._alive: asyncio.Task[None] | None = None

    async def _record(self) -> str:
        if self.record_id is None:
            self.record_id = await self._store.open_record()
            self._alive = self._store.keep_alive(self.record_id)
        return self.record_id

    async def __call__(self, old: str, new: str, old_type: str) -> None:
        await self._store._add_to_record(await self._record(), links=[(old, new, old_type)])

    async def superseded(self, old: str, new: str) -> None:
        """The node the write corrects and its new revision (ADR-109 Amendment 12): every alert
        naming it among its referents is renamed once the graph shows the commit."""
        await self._store._add_to_record(await self._record(), referents=[(old, new)])

    async def _left(self, *, failed: bool) -> None:
        if self._alive is not None:
            await self._store.stop_keeping_alive(self._alive)
        if failed and self.record_id is not None:
            # The writer raised or was cancelled, so its committer never commits (the worker rolls
            # back on any handler's exception, and a cancelled worker sends no commit; a caller of
            # `submit_supersede_node` must roll back too): nothing it recorded lands. A failure to
            # close is logged, never raised in place of the writer's own: the record then waits
            # for the stale threshold, its keep-alive stopped.
            try:
                await self._store._close_record(self.record_id)
            except Exception:  # noqa: BLE001
                _log.exception("repoint record %s left for the stale threshold", self.record_id)


@asynccontextmanager
async def journal_outside_commit(
    alerts: AlertStore | None,
) -> AsyncIterator[OutsideCommitJournal | None]:
    """`OutsideCommitJournal` over `alerts`, kept live while the block runs; `None` (nothing
    recorded) for a writer given no alert store, as `repointing_alerts` answers one. Leaving by
    an exception or a cancellation closes the record: the transaction's committer never commits
    it. A failure after the block (the caller's own work before its committer's commit) leaves the
    record, its keep-alive stopped, to the stale threshold, which drops it as never committed."""
    if alerts is None:
        yield None
        return
    journal = OutsideCommitJournal(alerts)
    left = False
    try:
        yield journal
        left = True
    finally:
        # `finally`, not `except Exception`: a cancellation (`BaseException`) must stop the
        # keep-alive too, or a record whose write never commits is marked live for good.
        await journal._left(failed=not left)


async def supersede_journalled[T](
    alerts: AlertStore | None,
    graph: GraphPort,
    write: Callable[[str, SupersedeJournal], Awaitable[T]],
    *,
    working_set: Any = None,
    superseding: str | None = None,
) -> T:
    """One graph transaction that supersedes what alerts may cite, through the repoint journal
    (ADR-109 Amendments 10 and 11), for a writer that commits its own transaction (the confirm and
    retract routes, the pipeline's enrich stage). `write(tx, journal)` does the writing and
    reports each replaced link through `journal` (`on_link_cloned`) and each node it corrects
    through `journal.superseded` before this commits; a write refused before its commit says so
    (`never_committed`). `superseding`, for a write of one node's correction that returns the new
    revision's id (the confirm and retract routes): that node and the id returned are recorded
    as `journal.superseded` would record them (ADR-109 Amendment 12). The moved alerts' re-marked
    nodes leave `working_set`, where one is held; else the next working-set read purges them
    (`purge_remarked_copies`)."""
    async with repointing_alerts(alerts, graph) as repoint:
        tx = await graph.begin_transaction()
        try:
            result = await write(tx, repoint)
            if superseding is not None:
                await repoint.superseded(superseding, str(result))
        except Exception:
            # Its commit never sent, nothing recorded can land: the record goes with it.
            repoint.never_committed()
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
    if working_set is not None and repoint.remarked_nodes:
        await purge_copies(working_set, repoint.remarked_nodes)
        await repoint.purged()
    return result


async def purge_copies(working_set: Any, nodes: Sequence[str]) -> None:
    """`nodes`' copies leave every working set that stored one
    (`WorkingSetService.remove_reverted`), and each case's stored removal is published on its
    channel at once (`notify.publish_delta`), so a connected canvas drops the copies now,
    projected for its reader, rather than at its next resynchronisation (ADR-109 Amendment 11,
    closing Amendment 10 point 6's second gap). Every store is cleared before anything is
    published, as the revert's own purge does (`working_set_revert.py`). A service built without
    a client (a test's) publishes nothing. The removal is the revert's own
    (`working_set_revert.remove_and_publish`). It does not scrub the named-step history, as the
    revert does: history serves no copy (its list is metadata only, and a restore re-reads the
    Vault, which returns no superseded node), and the superseded revision stays in the Vault itself,
    so a stored body there is no copy beyond it (ADR-109 Amendment 12, L2.8c's carry (c))."""
    from .working_set_revert import remove_and_publish

    await remove_and_publish(working_set, working_set.publisher, nodes, [])


async def purge_remarked_copies(alerts: AlertStore, working_set: Any) -> None:
    """Before a working-set read: the nodes a settle re-marked (on a read path, which holds no
    working sets) leave every working set that stored a copy at the old marking
    (`WorkingSetService.remove_reverted`), and their records are closed (ADR-109 Amendment 10;
    L2.8b's R2). A stored copy is served from the store, not read again from the graph."""
    for record_id, nodes in await alerts.applied_purges():
        await purge_copies(working_set, nodes)
        await alerts.purged(record_id)


async def settle_repoints(store: AlertStore, graph: GraphPort) -> None:
    """`AlertStore.settle_pending`, before a read of alerts. Every store the reads are given keeps
    the journal; one without `settle_pending` is refused (`AttributeError`), never passed over, so
    no read is answered from a store that could not have settled (L2.8c, ADR-109 Amendment 11)."""
    await store.settle_pending(graph)


async def evidence_available(
    alert: Alert, principal: Principal, graph: GraphPort, analytics: AnalyticsPort, *, case: str
) -> bool:
    """The read-time recheck `06_DECISIONS.md` ADR-039 requires — never trusted from write time.
    `NOTIFY_STUB` alerts have nothing to recheck (`Alert.mode`'s own docstring: no referent is ever
    stored for one) and are always "available" in this narrow sense. A `FULL` alert's evidence is
    available only if *every* node, link and transaction it cites (and its own `Alert` node) is
    visible to `principal` right now — one hidden piece withdraws the whole alert's evidence, and
    with it its words (ADR-146 decision 10, gap map G3). Its transactions are read in the reader's
    own `case`, as the queue reads them: the analytics store's case is a filter, not an access
    check, so reading them in the case the alert was raised in would give a reader that case's
    transactions without asking whether they may view it (rule 3; L2.8b's R1)."""
    if alert.mode is AlertMode.NOTIFY_STUB:
        return True
    readable = await read_evidence(
        [alert], principal, graph, analytics, scope=lambda _: case
    )
    return readable.whole(alert)


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
    "raiser_floor",
    "raiser_read_admits",
    "raiser_reads_admitting",
    "queue_scope",
    "DisclosurePolicy",
    "disclosure_policy_from_value",
    "evidence_available",
    "record_match",
]
