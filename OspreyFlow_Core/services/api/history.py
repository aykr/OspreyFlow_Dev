"""Named-step history — `spec/03_CONDUIT_MIDDLEWARE.md` §3.1's two routes,
pulled forward as the "named-step history with
restore" capability (the generic mechanism only — the rest of §3.1's "Network
analysis" table, Search Around/Pathfinder/Branch-to-new-tab, stays out of
scope for this phase).

**A step is a full membership snapshot, not a diff.** After every
working-set mutation that changes membership (seed, expand, remove, branch,
a future reproject), `app.py` records one row here holding the *complete*
source-fidelity (unfiltered) node/edge bodies at that moment — not just
ids, and not a delta to replay. Two reasons neither of those simpler shapes
works:

1. The Valkey delta stream is capped (`working_set/store.py`'s
   `DELTA_STREAM_MAXLEN`) and pruned — a diff-based history reachable only
   by replaying from the nearest snapshot would silently break the moment a
   step's chain crosses a pruned boundary, for a heavily-expanded,
   long-running investigation exactly the case history exists to serve.
2. `GraphPort` has no batch node/edge lookup by id and no `get_edge` at
   all (`packages/ports/graph.py`) — an id-only record could not be turned
   back into bodies at restore time without a port change this phase does
   not need, since the working-set store already holds the full bodies at
   the moment a step is written (`WorkingSetService.current_membership`).

**Restore re-projects handling fresh, against the requesting principal, not
whoever wrote the step.** `record_step` stores the *unfiltered* bodies
precisely so this is possible: `WorkingSetService.restore` runs the same
`_project` every other read uses before anything reaches the store or the
client, so a principal whose access has narrowed since — or a different,
less-privileged principal on a shared investigation — never sees content
visible only at record time. The narrower-clearance re-projection is
`tests/services/api/working_set/test_service.py`'s job, which
`tests/services/api/test_history_routes.py`'s own header also says.
(Until 25 September 2026 this named a test_history.py under that
directory — a file that has never existed. The case is real; the path was
not, and `tools/doc_citations_check.py` now catches the class.)

**Storage-scaling assumption, named rather than left implicit.** A full
node/edge body snapshot per mutating action means a long-running,
heavily-expanded investigation accumulates one row here per action, each
potentially holding tens of thousands of bodies. That is the right
trade-off for restore correctness now — the alternative shapes above are
each broken in a different way — but it is a real scaling assumption, not a
settled one: no retention or compaction policy exists yet. Recorded here in
the same spirit `duration_s` is noted elsewhere as "unexercised … noted
rather than forced, correctly", not left undocumented.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import asyncpg
from pydantic import BaseModel

from conduit_common.identity import new_id
from schemas.domain import Edge, Node

from .history_labels import CHANGED, FIXED_LABELS, NOT_RESTORABLE

_SHOWN_LABELS = FIXED_LABELS | {CHANGED}

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS investigation_history (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL,
    nodes JSONB NOT NULL,
    edges JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS investigation_history_investigation_id_idx
    ON investigation_history (investigation_id);
"""


#: Rewrites stored labels to the fixed texts of `history_labels.py` (ADR-124 decision 8). Run on
#: every start by `connect`, so it is idempotent: a fixed text matches no pattern below (each
#: pattern has text after the part that varied, which a fixed text lacks), and the last statement
#: leaves a fixed text alone. One pattern per site that used to write a count, a case id or an
#: alert's typology into its label. The patterns are plain words and spaces with `%` for the part
#: that varied; none has a `_` (a single-character wildcard in `LIKE`), and a test holds it so.
#: Anything matching none of them, such as a label a person's earlier build wrote, is `Changed`.
RELABEL_SQL = """
UPDATE investigation_history SET label = 'Branched' WHERE label LIKE 'Branched from %';
UPDATE investigation_history SET label = 'Seeded' WHERE label LIKE 'Seeded % node(s)';
UPDATE investigation_history SET label = 'Expanded' WHERE label LIKE 'Expanded % node(s) from %';
UPDATE investigation_history SET label = 'Showed links among the view'
    WHERE label LIKE 'Showed % link(s) among the nodes in view';
UPDATE investigation_history SET label = 'Showed links among the view'
    WHERE label LIKE 'Showed the routes within %';
UPDATE investigation_history SET label = 'Removed' WHERE label LIKE 'Removed % node(s)';
UPDATE investigation_history SET label = 'Ran a starter question'
    WHERE label LIKE 'Ran a starter question: %';
UPDATE investigation_history SET label = 'Showed two who share contacts'
    WHERE label LIKE 'Showed two who share contacts: %';
UPDATE investigation_history SET label = 'Opened from an alert'
    WHERE label LIKE 'Opened from alert %';
UPDATE investigation_history SET label = 'Showed an ownership structure'
    WHERE label LIKE 'Showed an ownership structure: %';
UPDATE investigation_history SET label = 'Opened an alert' WHERE label LIKE 'Opened an alert: %';
UPDATE investigation_history SET label = 'Changed' WHERE label NOT IN (
    'Branched', 'Seeded', 'Expanded', 'Showed links among the view', 'Removed',
    'Ran a starter question', 'Showed two who share contacts', 'Opened from an alert',
    'Showed an ownership structure', 'Opened an alert', 'Edited the brief', 'Changed'
);
"""


class HistoryStep(BaseModel):
    id: str
    investigation_id: str
    seq: int
    label: str
    created_at: datetime
    created_by: str
    nodes: list[Node]
    edges: list[Edge]


class HistoryStepSummary(BaseModel):
    """`GET /history`'s wire shape — metadata only: no node or edge bodies, and no size either
    (ADR-124 decision 8). A step's size was counted over the stored snapshot, which is unfiltered,
    so it was a figure for material the reader may not be entitled to read. The label is fixed text
    (`history_labels.py`). The bodies are not handed over until a specific step is restored, which
    re-applies the handling filter first."""

    id: str
    label: str
    created_at: datetime
    #: False for a step that holds no canvas snapshot (ADR-128: an edit to the case brief). The
    #: Glass offers no Restore for it and the restore route refuses it.
    restorable: bool = True


class HistoryStepNotFoundError(Exception):
    """`app.py`'s route already depends on `get_authorized_investigation`,
    so by the time this is raised the principal is already known to own the
    investigation — an unknown `step_id` within it is an ordinary 404, not
    an existence-leak case the way an unknown investigation id is."""


class InvestigationHistoryStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> InvestigationHistoryStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        store = cls(pool)
        await store.relabel()
        return store

    async def relabel(self) -> None:
        """Rewrite stored labels to the fixed texts (`RELABEL_SQL`). Safe to run again."""
        async with self._pool.acquire() as conn:
            await conn.execute(RELABEL_SQL)

    async def close(self) -> None:
        await self._pool.close()

    async def record_step(
        self,
        investigation_id: str,
        *,
        seq: int,
        label: str,
        created_by: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> HistoryStep:
        step = HistoryStep(
            id=new_id(),
            investigation_id=investigation_id,
            seq=seq,
            label=label,
            created_at=datetime.now(UTC),
            created_by=created_by,
            nodes=nodes,
            edges=edges,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO investigation_history "
                "(id, investigation_id, seq, label, created_at, created_by, nodes, edges) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                step.id,
                step.investigation_id,
                step.seq,
                step.label,
                step.created_at,
                step.created_by,
                json.dumps([n.model_dump(mode="json") for n in nodes]),
                json.dumps([e.model_dump(mode="json") for e in edges]),
            )
        return step

    async def remove_elements(self, node_ids: Sequence[str], edge_ids: Sequence[str]) -> int:
        """Takes these nodes and links out of **every** stored step, and any link in a step that
        ends at one of the nodes (ADR-127 decision 6: a revert takes back a load's elements, and no
        case's snapshot keeps their bodies). Not scoped to a case or a reader, as the revert is
        not: it removes the load's own elements. Every other element, and the order of the rest,
        is as it was. Returns how many steps changed, so a second call returns 0.

        Restore re-reads the Vault, where a reverted element is not read, so none would come back
        in any case; this is so the stored bodies, which are unfiltered, do not outlive it. Reads
        every step that holds one of the ids (no index serves a body's element ids), once per
        revert."""
        if not node_ids and not edge_ids:
            return 0
        nodes, edges = list(dict.fromkeys(node_ids)), list(dict.fromkeys(edge_ids))
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                "UPDATE investigation_history SET "
                "nodes = COALESCE((SELECT jsonb_agg(n.value ORDER BY n.ord) "
                "FROM jsonb_array_elements(nodes) WITH ORDINALITY AS n(value, ord) "
                "WHERE NOT (n.value->>'id' = ANY($1::text[]))), '[]'::jsonb), "
                "edges = COALESCE((SELECT jsonb_agg(e.value ORDER BY e.ord) "
                "FROM jsonb_array_elements(edges) WITH ORDINALITY AS e(value, ord) "
                "WHERE NOT (e.value->>'id' = ANY($2::text[]) "
                "OR e.value->>'source' = ANY($1::text[]) "
                "OR e.value->>'target' = ANY($1::text[]))), '[]'::jsonb) "
                "WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(nodes) AS n "
                "WHERE n->>'id' = ANY($1::text[])) "
                "OR EXISTS (SELECT 1 FROM jsonb_array_elements(edges) AS e "
                "WHERE e->>'id' = ANY($2::text[]) "
                "OR e->>'source' = ANY($1::text[]) OR e->>'target' = ANY($1::text[]))",
                nodes,
                edges,
            )
        return int(status.split()[-1])

    async def list_steps(self, investigation_id: str) -> list[HistoryStepSummary]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, label, created_at "
                "FROM investigation_history WHERE investigation_id = $1 "
                "ORDER BY seq ASC, created_at ASC",
                investigation_id,
            )
        # A label that is not fixed text is shown as `Changed`, whatever is stored: in a rolling
        # upgrade an old instance can still write a numbered label after `relabel` has run.
        shown = [row["label"] if row["label"] in _SHOWN_LABELS else CHANGED for row in rows]
        return [
            HistoryStepSummary(
                **{**dict(row), "label": label, "restorable": label not in NOT_RESTORABLE}
            )
            for row, label in zip(rows, shown, strict=True)
        ]

    async def last_seq(self, investigation_id: str) -> int:
        """The sequence number of the case's latest step, 0 for a case with none. A step that is
        not a canvas change (a brief edit) takes it, so the working set's own sequence, which the
        change stream's clients count, is not moved by it."""
        async with self._pool.acquire() as conn:
            latest = await conn.fetchval(
                "SELECT COALESCE(MAX(seq), 0) FROM investigation_history "
                "WHERE investigation_id = $1",
                investigation_id,
            )
        return int(latest)

    async def get_step(self, investigation_id: str, step_id: str) -> HistoryStep:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, investigation_id, seq, label, created_at, created_by, "
                "nodes, edges "
                "FROM investigation_history WHERE investigation_id = $1 AND id = $2",
                investigation_id,
                step_id,
            )
        if row is None:
            raise HistoryStepNotFoundError(step_id)
        data = dict(row)
        data["nodes"] = json.loads(data["nodes"])
        data["edges"] = json.loads(data["edges"])
        return HistoryStep(**data)
