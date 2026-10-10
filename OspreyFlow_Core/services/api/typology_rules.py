"""`TypologyRuleStore` — the deployed typology rules of each case (`06_DECISIONS.md` ADR-109
phase A). Same shape as every other control-plane store: Postgres, small, bootstrapped with
`CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`.

**Case-scoped, like the case's questions (`questions.py`).** A rule belongs to its case (ruling 3:
its alerts are the case team's queue), so reads take the case id; whether the caller may open the
case is the route's own level check (Author to deploy and retire, ruling 4). Within the case, the
dataset reach applies (`reach_clause`, ADR-099 Amendment 3). `list_active_for_case` is the
evaluator's system read, never exposed through a route.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg
from pydantic import TypeAdapter

from conduit_common.identity import new_id
from schemas.domain import (
    Principal,
    TypologyParams,
    TypologyRule,
    TypologyRuleInput,
)

from .dataset_scope import made_in, reach_clause

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS typology_rules (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    params JSONB NOT NULL,
    trigger TEXT NOT NULL,
    budget_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL,
    retired_at TIMESTAMPTZ,
    dataset_id TEXT
);
CREATE INDEX IF NOT EXISTS typology_rules_investigation_idx ON typology_rules (investigation_id);
"""

_COLUMNS = (
    "id, investigation_id, owner_id, name, params, trigger, budget_ms, status, created_at, "
    "retired_at, dataset_id"
)

_PARAMS: TypeAdapter[Any] = TypeAdapter(TypologyParams)


class TypologyRuleNotFoundError(Exception):
    """No such rule in this case, within the caller's reach — or already retired, for a retire."""


def _row_to_rule(row: asyncpg.Record) -> TypologyRule:
    params = row["params"]
    return TypologyRule(
        id=row["id"],
        investigation_id=row["investigation_id"],
        owner_id=row["owner_id"],
        name=row["name"],
        params=_PARAMS.validate_python(json.loads(params) if isinstance(params, str) else params),
        trigger=row["trigger"],
        budget_ms=row["budget_ms"],
        status=row["status"],
        created_at=row["created_at"],
        retired_at=row["retired_at"],
        dataset_id=row["dataset_id"],
    )


class TypologyRuleStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> TypologyRuleStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self, principal: Principal, investigation_id: str, spec: TypologyRuleInput
    ) -> TypologyRule:
        rule = TypologyRule(
            **spec.model_dump(),
            id=new_id(),
            investigation_id=investigation_id,
            owner_id=principal.id,
            created_at=datetime.now(UTC),
            dataset_id=made_in(principal),
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO typology_rules ({_COLUMNS}) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                rule.id,
                rule.investigation_id,
                rule.owner_id,
                rule.name,
                rule.params.model_dump_json(),
                rule.trigger,
                rule.budget_ms,
                rule.status,
                rule.created_at,
                rule.retired_at,
                rule.dataset_id,
            )
        return rule

    async def list_for_case(
        self, investigation_id: str, principal: Principal
    ) -> list[TypologyRule]:
        """Every rule of the case within the caller's dataset reach, newest first, retired ones
        included (the record of what ran stays readable)."""
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM typology_rules WHERE investigation_id = $1{reach} "
                "ORDER BY created_at DESC",
                investigation_id,
                *extra,
            )
        return [_row_to_rule(r) for r in rows]

    async def get_for_case(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> TypologyRule:
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM typology_rules "
                f"WHERE id = $1 AND investigation_id = $2{reach}",
                rule_id,
                investigation_id,
                *extra,
            )
        if row is None:
            raise TypologyRuleNotFoundError(rule_id)
        return _row_to_rule(row)

    async def retire(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> TypologyRule:
        """Retired, never deleted: the audit names it and its alerts cite it."""
        reach, extra = reach_clause(principal, 4)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE typology_rules SET status = 'retired', retired_at = $3 "
                f"WHERE id = $1 AND investigation_id = $2 AND status = 'active'{reach} "
                f"RETURNING {_COLUMNS}",
                rule_id,
                investigation_id,
                datetime.now(UTC),
                *extra,
            )
        if row is None:
            raise TypologyRuleNotFoundError(rule_id)
        return _row_to_rule(row)

    async def list_active_for_case(self, investigation_id: str) -> list[TypologyRule]:
        """The evaluator's population read — not principal-scoped (each rule then evaluates as its
        own deployer, ADR-036); never exposed through a route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM typology_rules "
                "WHERE investigation_id = $1 AND status = 'active' ORDER BY created_at",
                investigation_id,
            )
        return [_row_to_rule(r) for r in rows]


__all__ = ["TypologyRuleNotFoundError", "TypologyRuleStore"]
