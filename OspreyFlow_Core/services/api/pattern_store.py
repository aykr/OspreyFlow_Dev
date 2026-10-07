"""Saved-pattern persistence — `spec/02_GLASS_FRONTEND.md` §3.3's "saveable ... and versioned"
promise for `PatternQuery`, closed for save/load/list/version by `06_DECISIONS.md` ADR-032/036/
040 (Phase 7 Stage 4's own unfinished business, not Stage 6's).

Same shape as `investigations.py`/`sites.py`: small, relational, control-plane metadata,
Postgres-backed rather than a fourth store — a saved pattern is a query definition an analyst
wants to keep, not graph content and not ephemeral working-set state.

**Deliberately not `owning_unit`-scoped, unlike `Investigation`/`Site`.** ADR-036 and ADR-040 both
require a saved pattern readable only by its own **owner** (`principal.id`) until ADR-040 (pattern
sharing) is accepted — there is no `owning_unit`/share column to widen by mistake because sharing
does not exist yet. `PatternNotFoundError` collapses "no such pattern" and "exists, not yours"
into one response, the same existence-leak discipline `InvestigationNotFoundError`/
`SiteNotFoundError` already establish.

**Versioning.** `pattern_id` is stable across saves; each save under an existing `pattern_id`
inserts a new row with `version = <current max> + 1` rather than mutating a row in place — an
`UPDATE` would make a "version" promise this store cannot keep, since a prior version would no
longer exist to load. `get`/`get_authorized` without an explicit `version` return the latest.
`list_authorized` returns one row per `pattern_id` — the latest version owned by the calling
principal — not every version: a list of pattern *names* is what an analyst choosing what to load
needs, and every row already belongs to the calling principal, so no existence-leak question
arises the way it does for a hotlist (`06_DECISIONS.md` ADR-038's own "count, ordering" framing
does not apply here — there is no second, non-owning viewer of this list at all)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg

from conduit_common.identity import new_id
from schemas.domain import PatternQuery, Principal, SavedPattern

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS saved_patterns (
    id TEXT PRIMARY KEY,
    pattern_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    definition TEXT NOT NULL,
    UNIQUE (pattern_id, version)
);
CREATE INDEX IF NOT EXISTS saved_patterns_pattern_id_idx ON saved_patterns (pattern_id);
CREATE INDEX IF NOT EXISTS saved_patterns_owner_id_idx ON saved_patterns (owner_id);
-- ADR-099 Amendment 3: the dataset a pattern belongs to; none for one saved before it.
ALTER TABLE saved_patterns ADD COLUMN IF NOT EXISTS dataset_id TEXT;
"""


class PatternNotFoundError(Exception):
    """Also raised — deliberately, not a 403 — when the pattern exists but `owner_id` does not
    match the calling principal: the same existence-leak discipline `InvestigationNotFoundError`
    already applies extends to a saved pattern's own id, and (per ADR-040, not yet accepted) will
    extend to any future share target the same way."""


def _row_to_model(row: asyncpg.Record) -> SavedPattern:
    return SavedPattern(
        id=row["id"],
        pattern_id=row["pattern_id"],
        version=row["version"],
        name=row["name"],
        owner_id=row["owner_id"],
        created_at=row["created_at"],
        definition=PatternQuery.model_validate(json.loads(row["definition"])),
        dataset_id=row["dataset_id"],
    )


def _in_reach(principal: Principal, position: int) -> tuple[str, list[object]]:
    """ADR-099 Amendment 3, in the query itself: a pattern of one of the case's datasets, or one
    saved before that names none. The Conduit's own unlimited work (`datasets is None`) reads
    all."""
    if principal.datasets is None:
        return "", []
    return (
        f" AND (dataset_id = ANY(${position}::text[]) OR dataset_id IS NULL)",
        [list(principal.datasets)],
    )


class PatternStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PatternStore:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def save(
        self,
        principal: Principal,
        *,
        pattern_id: str | None,
        name: str,
        definition: PatternQuery,
    ) -> SavedPattern:
        """`pattern_id=None` starts a new pattern at version 1. A given `pattern_id` must already
        be owned by `principal` (checked via `get_authorized`, so a mismatched owner gets the same
        `PatternNotFoundError` as a typo'd id, not a distinguishable 403) and is saved as the next
        version — never an `UPDATE`, so every prior version stays loadable."""
        if pattern_id is None:
            new_pattern_id = new_id()
            version = 1
            dataset_id = principal.datasets[0] if principal.datasets else None
        else:
            existing = await self.get_authorized(pattern_id, principal)
            new_pattern_id = existing.pattern_id
            version = existing.version + 1
            # A new version stays in its pattern's dataset (one saved before keeps none).
            dataset_id = existing.dataset_id

        saved = SavedPattern(
            id=new_id(),
            pattern_id=new_pattern_id,
            version=version,
            name=name,
            owner_id=principal.id,
            created_at=datetime.now(UTC),
            definition=definition,
            dataset_id=dataset_id,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO saved_patterns "
                "(id, pattern_id, version, name, owner_id, created_at, definition, dataset_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                saved.id,
                saved.pattern_id,
                saved.version,
                saved.name,
                saved.owner_id,
                saved.created_at,
                json.dumps(saved.definition.model_dump(mode="json")),
                saved.dataset_id,
            )
        return saved

    async def get(self, pattern_id: str, *, version: int | None = None) -> SavedPattern:
        """No authorization check here — this is the raw record lookup. `get_authorized` is what
        every route actually uses. `version=None` returns the latest."""
        async with self._pool.acquire() as conn:
            if version is None:
                row = await conn.fetchrow(
                    "SELECT id, pattern_id, version, name, owner_id, created_at, definition, "
                    "dataset_id FROM saved_patterns WHERE pattern_id = $1 "
                    "ORDER BY version DESC LIMIT 1",
                    pattern_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT id, pattern_id, version, name, owner_id, created_at, definition, "
                    "dataset_id FROM saved_patterns WHERE pattern_id = $1 AND version = $2",
                    pattern_id,
                    version,
                )
        if row is None:
            raise PatternNotFoundError(pattern_id)
        return _row_to_model(row)

    async def get_authorized(
        self, pattern_id: str, principal: Principal, *, version: int | None = None
    ) -> SavedPattern:
        """The one method every route should call. `owner_id` is filtered in the query itself,
        not after fetch — the same shape `ExtractionCandidateStore.get_authorized`/
        `get_document_text` (`services/api/review.py`) use — access control lives in the adapter
        even for a Conduit-internal Postgres store like this one, not only the four ports: existence
        and content are refused by the same query, not a fetch followed by a Python-side check
        that already holds what it is about to reject. `review.py`'s own disclosed gap
        ("the twenty-two `review.py` tests that passed identically either
        side of the real `AND owning_unit = $2` fix") is exactly this class of bug, already found
        and fixed once elsewhere in this codebase — not reintroduced here."""
        async with self._pool.acquire() as conn:
            if version is None:
                reach, extra = _in_reach(principal, 3)
                row = await conn.fetchrow(
                    "SELECT id, pattern_id, version, name, owner_id, created_at, definition, "
                    "dataset_id FROM saved_patterns WHERE pattern_id = $1 AND owner_id = $2"
                    f"{reach} ORDER BY version DESC LIMIT 1",
                    pattern_id,
                    principal.id,
                    *extra,
                )
            else:
                reach, extra = _in_reach(principal, 4)
                row = await conn.fetchrow(
                    "SELECT id, pattern_id, version, name, owner_id, created_at, definition, "
                    "dataset_id FROM saved_patterns WHERE pattern_id = $1 AND owner_id = $2 "
                    f"AND version = $3{reach}",
                    pattern_id,
                    principal.id,
                    version,
                    *extra,
                )
        if row is None:
            raise PatternNotFoundError(pattern_id)
        return _row_to_model(row)

    async def list_authorized(self, principal: Principal) -> list[SavedPattern]:
        """The latest version of every pattern `principal` owns — never another principal's
        patterns, since sharing does not exist yet (ADR-040). Ordered most-recently-saved first."""
        reach, extra = _in_reach(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, pattern_id, version, name, owner_id, created_at, definition, "
                "dataset_id FROM (SELECT DISTINCT ON (pattern_id) * FROM saved_patterns"
                f"  WHERE owner_id = $1{reach} ORDER BY pattern_id, version DESC"
                ") latest ORDER BY created_at DESC",
                principal.id,
                *extra,
            )
        return [_row_to_model(row) for row in rows]


__all__ = [
    "PatternNotFoundError",
    "PatternStore",
]
