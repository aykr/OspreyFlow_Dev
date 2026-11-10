"""`scripts.migrate_rules_to_datasets` against real Postgres, under the stack lease, in a schema of
its own (`spec/06_DECISIONS.md` ADR-146 decision 3, Amendment 6, L2.11): the dry run, at `_main`
itself, changes no table, column, index or row; the real run leaves no whole-deployment rule and one
rule per dataset with the same conditions; a second run changes nothing.

Its own schema because the migration converts every whole-deployment rule in the database, and other
tests' rules in the shared one are theirs (asyncpg passes `search_path` on)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import asyncpg
import pytest
from conduit_common.identity import new_id
from schemas.domain import Principal, TypologyRuleInput
from schemas.sentences import RuleSentence, SentenceRuleParams
from scripts.migrate_rules_to_datasets import _main
from services.api.config import PostgresConfig
from services.api.typology_rules import TypologyRuleStore

ADMIN = Principal(id="admin", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
CONDITIONS = [{"op": "equals", "property": "family_name", "value": "Okafor"}]

_SHAPE = (
    "SELECT table_name, column_name, data_type FROM information_schema.columns "
    "WHERE table_schema = $1 ORDER BY 1, 2"
)


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"migrate_rules_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


async def _seed(dsn: str) -> str:
    """A whole-deployment rule, and two source datasets each with a home case: what a deployment
    from before L2.11 holds."""
    rules = await TypologyRuleStore.connect(dsn)
    try:
        sentence = RuleSentence.model_validate(
            {"subject": "Person", "conditions": CONDITIONS, "scope": "deployment"}
        )
        rule = await rules.create(ADMIN, "case-admin", TypologyRuleInput(
            name="Okafor anywhere", params=SentenceRuleParams(pattern_id="p", sentence=sentence)))  # fmt: skip
        await rules.approve(rule.id, "case-admin", ADMIN.model_copy(update={"id": "checker"}))
    finally:
        await rules.close()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "CREATE TABLE datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL); "
            "CREATE TABLE home_cases (dataset_id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL)"
        )
        await conn.executemany("INSERT INTO datasets VALUES ($1, $2, $3)", [
            ("ds-a", "Prison records", "source"), ("ds-b", "Custody suites", "source"),
            ("ds-both", "Both", "composite")])  # fmt: skip
        await conn.execute(
            "CREATE TABLE saved_patterns (id TEXT PRIMARY KEY, pattern_id TEXT NOT NULL, "
            "version INTEGER NOT NULL, name TEXT NOT NULL, owner_id TEXT NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL, definition TEXT NOT NULL, dataset_id TEXT)"
        )
        await conn.execute(
            "INSERT INTO saved_patterns VALUES ('sp-1', 'p', 1, 'Rule: Okafor anywhere', 'admin', "
            "now(), '{\"nodes\": [], \"edges\": []}', 'ds-admin')"
        )
        await conn.executemany("INSERT INTO home_cases VALUES ($1, $2)",
                               [("ds-a", "home-a"), ("ds-b", "home-b")])  # fmt: skip
        # The rule store as it stood before L2.11, so a dry run that opened it (whose `connect`
        # adds L2.11's columns and index) changes the shape and is caught.
        await conn.execute(
            "DROP INDEX typology_rule_versions_one_draft; ALTER TABLE typology_rule_versions "
            "DROP COLUMN tested_at, DROP COLUMN tested_by, DROP COLUMN tested_days, "
            "DROP COLUMN would_raise, DROP COLUMN asked_by, DROP COLUMN bpmn, DROP COLUMN dmn"
        )
    finally:
        await conn.close()
    return rule.id


async def _rows(conn: asyncpg.Connection) -> list[tuple[object, ...]]:
    rules = await conn.fetch("SELECT id, status, dataset_id, version FROM typology_rules ORDER BY id")
    versions = await conn.fetch(
        "SELECT rule_id, version, status FROM typology_rule_versions ORDER BY 1, 2"
    )
    return [tuple(r) for r in rules] + [tuple(v) for v in versions]


async def test_the_dry_run_at_its_real_call_site_changes_no_table_column_index_or_row(
    dsn: str,
) -> None:
    await _seed(dsn)
    conn = await asyncpg.connect(dsn)
    try:
        schema = await conn.fetchval("SELECT current_schema()")
        shape = await conn.fetch(_SHAPE, schema)
        indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = $1", schema)
        rows = await _rows(conn)
        assert await _main(["--dry-run"], dsn=dsn) == 0
        assert await conn.fetch(_SHAPE, schema) == shape
        assert await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE schemaname = $1", schema
        ) == indexes
        assert await _rows(conn) == rows
    finally:
        await conn.close()


async def test_the_real_run_leaves_no_whole_deployment_rule_and_one_per_dataset(dsn: str) -> None:
    wide = await _seed(dsn)
    assert await _main([], dsn=dsn) == 0
    conn = await asyncpg.connect(dsn)
    try:
        left = await conn.fetch(
            "SELECT id FROM typology_rules WHERE params->'sentence'->>'scope' = 'deployment' "
            "AND status <> 'retired'"
        )
        assert left == []
        copies = await conn.fetch(
            "SELECT investigation_id, dataset_id, status, params FROM typology_rules "
            "WHERE id <> $1 ORDER BY dataset_id",
            wide,
        )
        assert [(c["investigation_id"], c["dataset_id"], c["status"]) for c in copies] == [
            ("home-a", "ds-a", "active"), ("home-b", "ds-b", "active")]  # fmt: skip
        for copy in copies:
            params = json.loads(copy["params"])
            sentence = params["sentence"]
            assert sentence["conditions"] == CONDITIONS and sentence["scope"] == "this_case"
            # Each copy's own pattern, saved in its own dataset, which its runs read it within.
            mine = await conn.fetchval(
                "SELECT dataset_id FROM saved_patterns WHERE pattern_id = $1", params["pattern_id"]
            )
            assert mine == copy["dataset_id"]
        rows = await _rows(conn)
        assert await _main([], dsn=dsn) == 0  # a second run
        assert await _rows(conn) == rows
    finally:
        await conn.close()
