"""`TypologyRuleStore` — the deployed typology rules of each case (`06_DECISIONS.md` ADR-109
phase A). Same shape as every other control-plane store: Postgres, small, bootstrapped with
`CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`.

**Maker–checker (ADR-133 decision 7, stage (d)).** A whole-deployment rule is deployed `pending`,
and a change to or the retirement of one waits beside it as a pending version; it takes effect only
when a second person approves it (`approve`), never the person who proposed it (`OwnChangeRefused`).
Every change to every rule is kept in `typology_rule_versions`, with who proposed it and who decided
it; a change to a case rule is applied at once and kept the same way. A changed rule runs as the
person who wrote its new version: it is their pattern and their judgement now (ADR-036).

**The scheduled trigger's record (stage (d)).** Each slot of a scheduled rule is kept in
`rule_runs`, in words (`record_rule_run`, `rule_runs`).

**Checks on load (stage (d), decision 6).** A pipeline's chosen rules and what a hit does there are
kept in `recipe_load_checks`, keyed by the recipe; `None` means nobody has chosen, and every case
rule judges the pipeline's loads, as before the step existed.

**Case-scoped, like the case's questions (`questions.py`).** A rule belongs to its case (ruling 3:
its alerts are the case team's queue), so reads take the case id; whether the caller may open the
case is the route's own level check (Author to deploy and retire, ruling 4). Within the case, the
dataset reach applies (`reach_clause`, ADR-099 Amendment 3). `list_active_for_case` is the
evaluator's system read, never exposed through a route.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
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
from schemas.monitoring import LoadCheck, RuleRun, RuleVersion
from schemas.sentences import SentenceRuleParams

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
-- ADR-133 stage (d): a rule's current version.
ALTER TABLE typology_rules ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
CREATE TABLE IF NOT EXISTS typology_rule_versions (
    rule_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    action TEXT NOT NULL,
    name TEXT NOT NULL,
    params JSONB NOT NULL,
    trigger TEXT NOT NULL,
    budget_ms INTEGER NOT NULL,
    proposed_by TEXT NOT NULL,
    proposed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    words TEXT,
    PRIMARY KEY (rule_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS typology_rule_versions_one_pending
    ON typology_rule_versions (rule_id) WHERE status = 'pending';
-- Every rule from before stage (d) gets its first version, as it was deployed. A whole-deployment
-- rule went live then on one person's say (ADR-133 Amendment 2, item 7): it is made pending now,
-- its first version waiting for a second person.
INSERT INTO typology_rule_versions (rule_id, version, action, name, params, trigger, budget_ms,
    proposed_by, proposed_at, status, words)
SELECT id, 1, 'deploy', name, params, trigger, budget_ms, owner_id, created_at,
    CASE WHEN params->'sentence'->>'scope' = 'deployment' AND status = 'active' THEN 'pending'
         ELSE 'applied' END,
    CASE WHEN params->'sentence'->>'scope' = 'deployment' AND status = 'active'
         THEN 'deployed before a second person''s approval was needed; it waits for one now'
         ELSE NULL END
FROM typology_rules r
WHERE NOT EXISTS (SELECT 1 FROM typology_rule_versions v WHERE v.rule_id = r.id);
UPDATE typology_rules SET status = 'pending'
WHERE status = 'active' AND params->'sentence'->>'scope' = 'deployment'
  AND EXISTS (SELECT 1 FROM typology_rule_versions v WHERE v.rule_id = typology_rules.id
              AND v.version = 1 AND v.action = 'deploy' AND v.status = 'pending');
CREATE TABLE IF NOT EXISTS rule_runs (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    rule_version INTEGER NOT NULL,
    slot TIMESTAMPTZ NOT NULL,
    ran_at TIMESTAMPTZ NOT NULL,
    run_as TEXT NOT NULL,
    outcome TEXT NOT NULL,
    alerts INTEGER NOT NULL DEFAULT 0,
    words TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS rule_runs_rule_idx ON rule_runs (rule_id, slot DESC);
CREATE TABLE IF NOT EXISTS recipe_load_checks (
    recipe_id TEXT PRIMARY KEY,
    checks JSONB NOT NULL,
    set_by TEXT NOT NULL,
    set_at TIMESTAMPTZ NOT NULL
);
"""

_COLUMNS = (
    "id, investigation_id, owner_id, name, params, trigger, budget_ms, status, created_at, "
    "retired_at, dataset_id"
)
#: What a read returns: the stored columns, the current version, and the change waiting, if any.
_READ = (
    "id, investigation_id, owner_id, name, params, trigger, budget_ms, status, created_at, "
    "retired_at, dataset_id, version, "
    "(SELECT row_to_json(p) FROM (SELECT action, proposed_by, version "
    "FROM typology_rule_versions v "
    "WHERE v.rule_id = typology_rules.id AND v.status = 'pending') p) AS pending"
)
_VERSION_COLUMNS = (
    "rule_id, version, action, name, params, trigger, budget_ms, proposed_by, proposed_at, status, "
    "decided_by, decided_at, words"
)

_PARAMS: TypeAdapter[Any] = TypeAdapter(TypologyParams)

#: ADR-133 decision 1: a sentence deployed for the whole deployment watches every case's loads.
#: Read from the stored parameters, so no column is added and no stored row changes.
_DEPLOYMENT_WIDE = "params->'sentence'->>'scope' = 'deployment'"


def _deployment_wide(spec: TypologyRuleInput) -> bool:
    params = spec.params
    return isinstance(params, SentenceRuleParams) and params.sentence.scope == "deployment"


class TypologyRuleNotFoundError(Exception):
    """No such rule in this case, within the caller's reach — or already retired, for a retire."""


class RuleChangeRefused(Exception):
    """A change, approval or rejection that may not be made, in words."""


class OwnChangeRefused(RuleChangeRefused):
    """ADR-133 decision 7: the person who proposed a change cannot approve it."""


@dataclass(frozen=True)
class LoadChecksRecord:
    """A pipeline's chosen checks on load, and who chose them."""

    checks: list[LoadCheck]
    set_by: str
    set_at: datetime


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _row_to_rule(row: asyncpg.Record) -> TypologyRule:
    params = row["params"]
    keys = set(row.keys())
    pending = _json(row["pending"]) if "pending" in keys and row["pending"] is not None else None
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
        version=row["version"] if "version" in keys else 1,
        pending_action=pending["action"] if pending else None,
        pending_by=pending["proposed_by"] if pending else None,
        pending_version=pending["version"] if pending else None,
    )


def _row_to_version(row: asyncpg.Record) -> RuleVersion:
    return RuleVersion(
        rule_id=row["rule_id"],
        version=row["version"],
        action=row["action"],
        name=row["name"],
        params=_PARAMS.validate_python(_json(row["params"])),
        trigger=row["trigger"],
        budget_ms=row["budget_ms"],
        proposed_by=row["proposed_by"],
        proposed_at=row["proposed_at"],
        status=row["status"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        words=row["words"],
    )


def _row_to_run(row: asyncpg.Record) -> RuleRun:
    return RuleRun(**dict(row))


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
        """A rule deployed, its first version kept. A whole-deployment rule is `pending` until a
        second person approves it (decision 7); any other is live at once."""
        wide = _deployment_wide(spec)
        rule = TypologyRule(
            **spec.model_dump(),
            id=new_id(),
            investigation_id=investigation_id,
            owner_id=principal.id,
            created_at=datetime.now(UTC),
            # A deployment-wide sentence belongs to no one case's dataset: it watches every case.
            dataset_id=None if wide else made_in(principal),
            status="pending" if wide else "active",
        )
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"INSERT INTO typology_rules ({_COLUMNS}, version) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 1)",
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
            await self._keep_version(
                conn, rule.id, 1, "deploy", spec, principal.id, rule.created_at,
                status="pending" if wide else "applied",
            )  # fmt: skip
        return await self._read(rule.id)

    @staticmethod
    async def _keep_version(
        conn: asyncpg.Connection,
        rule_id: str,
        version: int,
        action: str,
        spec: TypologyRuleInput,
        by: str,
        at: datetime,
        *,
        status: str,
        words: str | None = None,
    ) -> None:
        await conn.execute(
            f"INSERT INTO typology_rule_versions ({_VERSION_COLUMNS}) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
            rule_id, version, action, spec.name, spec.params.model_dump_json(), spec.trigger,
            spec.budget_ms, by, at, status,
            by if status == "applied" else None, at if status == "applied" else None, words,
        )  # fmt: skip

    async def _read(self, rule_id: str) -> TypologyRule:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {_READ} FROM typology_rules WHERE id = $1", rule_id)
        if row is None:
            raise TypologyRuleNotFoundError(rule_id)
        return _row_to_rule(row)

    async def list_for_case(
        self, investigation_id: str, principal: Principal
    ) -> list[TypologyRule]:
        """Every rule of the case within the caller's dataset reach, newest first, retired ones
        included (the record of what ran stays readable) — and every deployment-wide sentence,
        which watches this case's loads too (ADR-133 decision 1)."""
        reach, extra = reach_clause(principal, 2)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_READ} FROM typology_rules "
                f"WHERE (investigation_id = $1 OR {_DEPLOYMENT_WIDE}){reach} "
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
                f"SELECT {_READ} FROM typology_rules "
                f"WHERE id = $1 AND investigation_id = $2{reach}",
                rule_id,
                investigation_id,
                *extra,
            )
        if row is None:
            raise TypologyRuleNotFoundError(rule_id)
        return _row_to_rule(row)

    async def get_listed(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> TypologyRule:
        """A rule as the case's rules list shows it: the case's own, or a whole-deployment one."""
        reach, extra = reach_clause(principal, 3)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_READ} FROM typology_rules "
                f"WHERE id = $1 AND (investigation_id = $2 OR {_DEPLOYMENT_WIDE}){reach}",
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
        """Retired, never deleted: the audit names it and its alerts cite it. The retirement is
        kept as a version. A whole-deployment rule is retired through `propose_retire`."""
        reach, extra = reach_clause(principal, 4)
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "UPDATE typology_rules SET status = 'retired', retired_at = $3, "
                "version = version + 1 "
                f"WHERE id = $1 AND investigation_id = $2 AND status = 'active'{reach} "
                f"RETURNING {_COLUMNS}, version",
                rule_id,
                investigation_id,
                now,
                *extra,
            )
            if row is None:
                raise TypologyRuleNotFoundError(rule_id)
            await self._keep_version(
                conn, rule_id, row["version"], "retire", _as_input(_row_to_rule(row)),
                principal.id, now, status="applied",
            )  # fmt: skip
        return await self._read(rule_id)

    # --- maker–checker (ADR-133 decision 7, stage (d)) ------------------------------------------

    async def propose_change(
        self,
        rule_id: str,
        investigation_id: str,
        principal: Principal,
        spec: TypologyRuleInput,
    ) -> TypologyRule:
        """A new version of the rule. Where the rule is, or would become, a whole-deployment rule,
        it waits for a second person and the rule runs as it stood meanwhile; otherwise it is
        applied at once. Either way it is kept, and the rule then runs as `principal`, who wrote
        it."""
        rule = await self.get_listed(rule_id, investigation_id, principal)
        if rule.status == "retired":
            raise RuleChangeRefused("a retired rule cannot be changed")
        if rule.pending_action is not None:
            raise RuleChangeRefused(
                "a change to this rule is already waiting for a second person's approval"
            )
        now = datetime.now(UTC)
        wide = _deployment_wide(_as_input(rule)) or _deployment_wide(spec)
        async with self._pool.acquire() as conn, conn.transaction():
            version = await self._next_version(conn, rule.id)
            await self._keep_version(
                conn, rule.id, version, "change", spec, principal.id, now,
                status="pending" if wide else "applied",
            )  # fmt: skip
            if not wide:
                await self._apply(conn, rule, spec, principal, version, dataset=made_in(principal))
        return await self._read(rule.id)

    async def propose_retire(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> TypologyRule:
        """Retires a case rule at once; a whole-deployment rule's retirement waits for a second
        person, the rule running meanwhile."""
        rule = await self.get_listed(rule_id, investigation_id, principal)
        if not _deployment_wide(_as_input(rule)):
            return await self.retire(rule_id, investigation_id, principal)
        if rule.status != "active":
            raise RuleChangeRefused("only a rule that is running can be retired")
        if rule.pending_action is not None:
            raise RuleChangeRefused(
                "a change to this rule is already waiting for a second person's approval"
            )
        async with self._pool.acquire() as conn, conn.transaction():
            version = await self._next_version(conn, rule.id)
            await self._keep_version(
                conn, rule.id, version, "retire", _as_input(rule), principal.id,
                datetime.now(UTC), status="pending",
            )  # fmt: skip
        return await self._read(rule.id)

    async def approve(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> TypologyRule:
        """The waiting change takes effect, decided by `principal` — never the person who proposed
        it. Read within the approver's reach, so a rule they cannot see is not found."""
        rule = await self.get_listed(rule_id, investigation_id, principal)
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f"SELECT {_VERSION_COLUMNS} FROM typology_rule_versions "
                "WHERE rule_id = $1 AND status = 'pending' FOR UPDATE",
                rule.id,
            )
            if row is None:
                raise RuleChangeRefused("nothing waiting for approval on this rule")
            waiting = _row_to_version(row)
            if waiting.proposed_by == principal.id:
                raise OwnChangeRefused(
                    "you proposed this change; a second person with the right must approve it"
                )
            await conn.execute(
                "UPDATE typology_rule_versions SET status = 'approved', decided_by = $3, "
                "decided_at = $4 WHERE rule_id = $1 AND version = $2",
                rule.id, waiting.version, principal.id, now,
            )  # fmt: skip
            spec = TypologyRuleInput(
                name=waiting.name, params=waiting.params, trigger=waiting.trigger,
                budget_ms=waiting.budget_ms,
            )  # fmt: skip
            if waiting.action == "deploy":
                await conn.execute(
                    "UPDATE typology_rules SET status = 'active' WHERE id = $1", rule.id
                )
            elif waiting.action == "retire":
                await conn.execute(
                    "UPDATE typology_rules SET status = 'retired', retired_at = $2, version = $3 "
                    "WHERE id = $1",
                    rule.id, now, waiting.version,
                )  # fmt: skip
            else:
                proposer = principal.model_copy(update={"id": waiting.proposed_by})
                dataset = None if _deployment_wide(spec) else rule.dataset_id
                await self._apply(conn, rule, spec, proposer, waiting.version, dataset=dataset)
        return await self._read(rule.id)

    async def reject(
        self, rule_id: str, investigation_id: str, principal: Principal, reason: str
    ) -> TypologyRule:
        """The waiting change is turned down, with the reason, and the rule stays as it was. A
        rejected deployment never ran: it is retired. Its proposer may withdraw it this way."""
        rule = await self.get_listed(rule_id, investigation_id, principal)
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "UPDATE typology_rule_versions SET status = 'rejected', decided_by = $2, "
                "decided_at = $3, words = $4 WHERE rule_id = $1 AND status = 'pending' "
                "RETURNING action",
                rule.id, principal.id, now, reason,
            )  # fmt: skip
            if row is None:
                raise RuleChangeRefused("nothing waiting for approval on this rule")
            if row["action"] == "deploy":
                await conn.execute(
                    "UPDATE typology_rules SET status = 'retired', retired_at = $2 WHERE id = $1",
                    rule.id, now,
                )  # fmt: skip
        return await self._read(rule.id)

    async def versions(
        self, rule_id: str, investigation_id: str, principal: Principal
    ) -> list[RuleVersion]:
        """Every version of a rule the reader may see, oldest first."""
        rule = await self.get_listed(rule_id, investigation_id, principal)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_VERSION_COLUMNS} FROM typology_rule_versions WHERE rule_id = $1 "
                "ORDER BY version",
                rule.id,
            )
        return [_row_to_version(r) for r in rows]

    @staticmethod
    async def _next_version(conn: asyncpg.Connection, rule_id: str) -> int:
        await conn.execute("SELECT 1 FROM typology_rules WHERE id = $1 FOR UPDATE", rule_id)
        latest = await conn.fetchval(
            "SELECT max(version) FROM typology_rule_versions WHERE rule_id = $1", rule_id
        )
        return int(latest or 0) + 1

    @staticmethod
    async def _apply(
        conn: asyncpg.Connection,
        rule: TypologyRule,
        spec: TypologyRuleInput,
        writer: Principal,
        version: int,
        *,
        dataset: str | None,
    ) -> None:
        await conn.execute(
            "UPDATE typology_rules SET name = $2, params = $3, trigger = $4, budget_ms = $5, "
            "owner_id = $6, version = $7, dataset_id = $8 WHERE id = $1",
            rule.id, spec.name, spec.params.model_dump_json(), spec.trigger, spec.budget_ms,
            writer.id, version, dataset,
        )  # fmt: skip

    # --- the evaluator's reads --------------------------------------------------------------------

    async def list_active_for_case(self, investigation_id: str) -> list[TypologyRule]:
        """The evaluator's population read — not principal-scoped (each rule then evaluates as its
        own deployer, ADR-036); never exposed through a route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_READ} FROM typology_rules "
                f"WHERE (investigation_id = $1 OR {_DEPLOYMENT_WIDE}) AND status = 'active' "
                "ORDER BY created_at",
                investigation_id,
            )
        return [_row_to_rule(r) for r in rows]

    async def list_active_of_typology(self, typology: str) -> list[TypologyRule]:
        """Every active rule of one typology, in every case — a screening list's re-screening
        reads each `kyc_screening` rule (ADR-133 decision 4). Not principal-scoped, like
        `list_active_for_case`: each rule then runs as its own deployer. Never a route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_READ} FROM typology_rules "
                "WHERE params->>'typology' = $1 AND status = 'active' ORDER BY created_at, id",
                typology,
            )
        return [_row_to_rule(r) for r in rows]

    # --- the scheduled trigger (ADR-133 decision 1, stage (d)) ------------------------------------

    async def scheduled_rules(self) -> list[TypologyRule]:
        """Every rule that runs on a schedule, whatever its status: the executor runs the active
        ones, and the record says why another does not. The scheduler's read, never a route."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_READ} FROM typology_rules WHERE trigger = 'schedule' "
                "ORDER BY created_at, id"
            )
        return [_row_to_rule(r) for r in rows]

    async def record_rule_run(self, run: RuleRun) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO rule_runs (id, rule_id, rule_version, slot, ran_at, run_as, outcome, "
                "alerts, words) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                run.id, run.rule_id, run.rule_version, run.slot, run.ran_at, run.run_as,
                run.outcome, run.alerts, run.words,
            )  # fmt: skip

    async def rule_runs(self, rule_id: str, *, limit: int = 20) -> list[RuleRun]:
        """A rule's latest runs, newest first. The route reads the rule within the reader's reach
        first; this is the record under it."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, rule_id, rule_version, slot, ran_at, run_as, outcome, alerts, words "
                "FROM rule_runs WHERE rule_id = $1 ORDER BY slot DESC, ran_at DESC LIMIT $2",
                rule_id,
                limit,
            )
        return [_row_to_run(r) for r in rows]

    async def last_rule_slot(self, rule_id: str) -> datetime | None:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT max(slot) FROM rule_runs WHERE rule_id = $1", rule_id
            )
        return value  # type: ignore[no-any-return]

    # --- checks on load (ADR-133 decision 6, stage (d)) -------------------------------------------

    async def load_checks(self, recipe_id: str) -> LoadChecksRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT checks, set_by, set_at FROM recipe_load_checks WHERE recipe_id = $1",
                recipe_id,
            )
        if row is None:
            return None
        return LoadChecksRecord(
            checks=[LoadCheck.model_validate(c) for c in _json(row["checks"])],
            set_by=row["set_by"],
            set_at=row["set_at"],
        )

    async def set_load_checks(
        self, recipe_id: str, checks: Sequence[LoadCheck], by: Principal
    ) -> LoadChecksRecord:
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO recipe_load_checks (recipe_id, checks, set_by, set_at) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (recipe_id) DO UPDATE SET "
                "checks = EXCLUDED.checks, set_by = EXCLUDED.set_by, set_at = EXCLUDED.set_at",
                recipe_id,
                json.dumps([c.model_dump() for c in checks]),
                by.id,
                now,
            )
        return LoadChecksRecord(checks=list(checks), set_by=by.id, set_at=now)


def _as_input(rule: TypologyRule) -> TypologyRuleInput:
    return TypologyRuleInput(
        name=rule.name, params=rule.params, trigger=rule.trigger, budget_ms=rule.budget_ms
    )


__all__ = [
    "LoadChecksRecord",
    "OwnChangeRefused",
    "RuleChangeRefused",
    "TypologyRuleNotFoundError",
    "TypologyRuleStore",
]
