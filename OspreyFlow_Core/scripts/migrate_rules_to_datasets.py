"""Converts every whole-deployment rule to one rule per dataset (`06_DECISIONS.md` ADR-146
decision 3 and Amendment 6, L2.11): "A whole-deployment rule is converted to one rule per dataset
by a one-off command, dry run first; the dry run writes nothing."

Run inside the deployment, where Postgres is reachable; the Conduit may keep running:

    python -m scripts.migrate_rules_to_datasets --dry-run   # says what it would do
    python -m scripts.migrate_rules_to_datasets             # does it

For each whole-deployment rule not yet retired, oldest first:

1. **One rule per source dataset**, in that dataset's home case (ADR-145 Amendment 4), declared on
   it, with the same conditions, the same owner and the same name. Its scope becomes *this case*.
   A composite gets none: it is read as its members, each of which has its own.
2. **Live stays live.** A rule that was running is copied running. One still waiting for its first
   approval is copied as a draft, which runs only once tested and made live.
3. **The original is retired**, with a version saying why. A change that was waiting on it is
   closed, in words.
4. **A dataset with no home case is reported, never guessed,** and the rule is left whole and
   running, converted to no dataset: copies beside a running original would raise every alert
   twice, and a rule retired before every dataset had its copy would leave that one unwatched. A
   second run, once the home case is made, converts it.

Each rule is converted in one transaction, so a failure part-way leaves it whole-deployment and
untouched. A second run finds no whole-deployment rule to convert and changes nothing.

**The dry run writes nothing by construction,** twice over. It never opens `TypologyRuleStore`,
whose `connect` adds columns, tables and indexes: it reads the rules, the datasets and the home
cases with plain `SELECT`s (`snapshot`). And every write the plan makes goes through `Recorded`,
which records it and makes nothing. `test_migrate_rules_to_datasets.py` shows the second red (a
writer that writes handed in); `test_migrate_rules_to_datasets_store.py` the first, at `_main`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg
from services.api.config import PostgresConfig
from services.api.typology_rules import TypologyRuleStore

from conduit_common.identity import new_id

ACTOR = "migrate-rules-to-datasets"
_WIDE = "params->'sentence'->>'scope' = 'deployment'"


@dataclass(frozen=True)
class WideRule:
    """A whole-deployment rule as stored."""

    id: str
    investigation_id: str
    owner_id: str
    name: str
    params: dict[str, Any]
    trigger: str
    budget_ms: int
    status: str
    version: int


@dataclass(frozen=True)
class SourceDataset:
    """A source dataset, and its home case if it has one."""

    id: str
    name: str
    home_case: str | None


@dataclass
class Report:
    #: (whole-deployment rule id, dataset id, the new rule's id).
    copied: list[tuple[str, str, str]] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    #: Each rule or dataset not converted, with why, in words.
    unplaced: list[str] = field(default_factory=list)
    #: Every write made (or, in a dry run, that would be made), in order.
    writes: list[str] = field(default_factory=list)


class Writer(Protocol):
    async def write(self, said: str, sql: str, *args: Any) -> None: ...


class Recorded:
    """A dry run's writer: records what it would write and writes nothing."""

    def __init__(self, writes: list[str]) -> None:
        self._writes = writes

    async def write(self, said: str, sql: str, *args: Any) -> None:
        self._writes.append(said)


class Written:
    """A real run's writer, on one connection inside the rule's transaction."""

    def __init__(self, conn: asyncpg.Connection, writes: list[str]) -> None:
        self._conn = conn
        self._writes = writes

    async def write(self, said: str, sql: str, *args: Any) -> None:
        await self._conn.execute(sql, *args)
        self._writes.append(said)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def snapshot(conn: asyncpg.Connection) -> tuple[list[WideRule], list[SourceDataset]]:
    """The whole-deployment rules not yet retired, oldest first, and every source dataset with its
    home case: `SELECT`s only, which read a deployment made before dataset kinds or home cases."""
    if not await conn.fetchval("SELECT to_regclass('typology_rules') IS NOT NULL"):
        return [], []
    version = (
        "version"
        if await conn.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'typology_rules' AND column_name = 'version'"
        )
        else "1 AS version"
    )
    rows = await conn.fetch(
        "SELECT id, investigation_id, owner_id, name, params, trigger, budget_ms, status, "
        f"{version} FROM typology_rules WHERE {_WIDE} AND status <> 'retired' "
        "ORDER BY created_at, id"
    )
    rules = [
        WideRule(
            id=r["id"], investigation_id=r["investigation_id"], owner_id=r["owner_id"],
            name=r["name"], params=_json(r["params"]), trigger=r["trigger"],
            budget_ms=r["budget_ms"], status=r["status"], version=r["version"],
        )
        for r in rows
    ]  # fmt: skip
    homes: dict[str, str] = {}
    if await conn.fetchval("SELECT to_regclass('home_cases') IS NOT NULL"):
        homes = {
            r["dataset_id"]: r["investigation_id"]
            for r in await conn.fetch("SELECT dataset_id, investigation_id FROM home_cases")
        }
    datasets: list[SourceDataset] = []
    if await conn.fetchval("SELECT to_regclass('datasets') IS NOT NULL"):
        for r in await conn.fetch("SELECT to_jsonb(d) AS row FROM datasets d"):
            row = _json(r["row"])
            if row.get("kind", "source") == "source":
                datasets.append(SourceDataset(row["id"], row["name"], homes.get(row["id"])))
    return rules, sorted(datasets, key=lambda d: d.id)


async def convert(
    rule: WideRule, datasets: Sequence[SourceDataset], writer: Writer, report: Report
) -> None:
    """One whole-deployment rule converted, every write through `writer`."""
    now = datetime.now(UTC)
    params = {**rule.params, "sentence": {**rule.params["sentence"], "scope": "this_case"}}
    live = rule.status == "active"
    words = f"Converted from the whole-deployment rule {rule.name!r} ({rule.id})."
    missing = [d for d in datasets if d.home_case is None]
    if missing:
        names = ", ".join(f"{d.name!r} ({d.id})" for d in missing)
        report.unplaced.append(
            f"{rule.name!r} ({rule.id}) left whole and running: {names} has no home case; make "
            "one and run this again"
        )
        return
    for dataset in datasets:
        assert dataset.home_case is not None
        copy_id = new_id()
        await writer.write(
            f"copy {rule.name!r} ({rule.id}) to {dataset.name!r} ({dataset.id}) in its home case "
            f"{dataset.home_case} as {'live' if live else 'a draft'}",
            "INSERT INTO typology_rules (id, investigation_id, owner_id, name, params, trigger, "
            "budget_ms, status, created_at, retired_at, dataset_id, version) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NULL, $10, 1)",
            copy_id, dataset.home_case, rule.owner_id, rule.name, json.dumps(params),
            rule.trigger, rule.budget_ms, "active" if live else "draft", now, dataset.id,
        )  # fmt: skip
        await writer.write(
            f"keep version 1 of {copy_id}",
            "INSERT INTO typology_rule_versions (rule_id, version, action, name, params, trigger, "
            "budget_ms, proposed_by, proposed_at, status, decided_by, decided_at, words) "
            "VALUES ($1, 1, 'deploy', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
            copy_id, rule.name, json.dumps(params), rule.trigger, rule.budget_ms, rule.owner_id,
            now, "applied" if live else "draft", ACTOR if live else None, now if live else None,
            words,
        )  # fmt: skip
        report.copied.append((rule.id, dataset.id, copy_id))
    await writer.write(
        f"close any change waiting on {rule.id}",
        "UPDATE typology_rule_versions SET status = 'rejected', decided_by = $2, decided_at = $3, "
        "words = $4 WHERE rule_id = $1 AND status = 'pending'",
        rule.id, ACTOR, now, "Converted to one rule per dataset before it was decided.",
    )  # fmt: skip
    await writer.write(
        f"retire {rule.name!r} ({rule.id})",
        "UPDATE typology_rules SET status = 'retired', retired_at = $2, version = $3 "
        "WHERE id = $1",
        rule.id, now, rule.version + 1,
    )  # fmt: skip
    await writer.write(
        f"keep the retirement of {rule.id} as version {rule.version + 1}",
        "INSERT INTO typology_rule_versions (rule_id, version, action, name, params, trigger, "
        "budget_ms, proposed_by, proposed_at, status, decided_by, decided_at, words) "
        "VALUES ($1, $2, 'retire', $3, $4, $5, $6, $7, $8, 'applied', $7, $8, $9)",
        rule.id, rule.version + 1, rule.name, json.dumps(rule.params), rule.trigger,
        rule.budget_ms, ACTOR, now, "Converted to one rule per dataset (ADR-146 decision 3).",
    )  # fmt: skip
    report.retired.append(rule.id)


async def migrate(
    rules: Sequence[WideRule],
    datasets: Sequence[SourceDataset],
    *,
    conn: asyncpg.Connection | None,
    write: bool,
) -> Report:
    """Every rule converted, each in its own transaction on a real run; recorded on a dry run."""
    report = Report()
    if not datasets and rules:
        report.unplaced.append("there is no source dataset to convert the rules to")
        return report
    for rule in rules:
        if not write:
            await convert(rule, datasets, Recorded(report.writes), report)
            continue
        assert conn is not None
        async with conn.transaction():
            await convert(rule, datasets, Written(conn, report.writes), report)
    return report


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="say what it would do; write nothing"
    )
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None, *, dsn: str | None = None) -> int:
    args = _parse(argv)
    write = not args.dry_run
    print("Dry run: nothing will be written." if not write else "Converting rules per dataset.")
    dsn = dsn or PostgresConfig.from_env().dsn
    if write:
        # The store's own bootstrap first, so the tables are as the Conduit keeps them.
        await (await TypologyRuleStore.connect(dsn)).close()
    conn = await asyncpg.connect(dsn)
    try:
        rules, datasets = await snapshot(conn)
        report = await migrate(rules, datasets, conn=conn if write else None, write=write)
    finally:
        await conn.close()
    for line in report.unplaced:
        print(f"  not converted: {line}")
    print(
        f"{len(rules)} whole-deployment rules; {len(report.copied)} copies "
        f"{'made' if write else 'to make'}, {len(report.retired)} retired; "
        f"{len(report.unplaced)} not converted; {len(report.writes)} writes "
        f"{'made' if write else 'that would be made'}."
    )
    print("Done." if write else "Dry run finished: nothing was written.")
    return 1 if report.unplaced else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
