"""`scripts.migrate_branches_to_views` through its own deployment reads and writes, against real
Postgres and a real ArcadeDB (a lane's leased test stack; L3.2 part D). The working sets stand in
(`FakeWorkingSetStore`), read for two things only: a case's node ids and its threshold.

The plan's rules are in `test_migrate_branches_to_views.py`; this proves the SQL the script runs
does what the plan says, in both stores: a dry run changes no row and no element, and a real run
leaves a view under the original holding the case's nodes, the case removed with its origin and
layer links dropped, and what the old case's own layer held in the original's layer, tagged.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import asyncpg
import pytest
from scripts.migrate_branches_to_views import (
    LEGACY_LAYER_MAKER,
    TAG,
    DeploymentReads,
    DeploymentWrites,
    DryRun,
    Report,
    migrate,
)
from scripts.stamp_datasets import _Sql, _type_names
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig
from services.api.datasets import PostgresDatasetStore
from services.api.investigations import InvestigationStore

from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from tests.services.api.unconverted import made_before_l3_2_on_postgres
from tests.services.api.working_set.fakes import FakeWorkingSetStore
from tests.services.api.working_set.test_visible_link import node

ONTOLOGY = load_default_ontology()
ALICE = Principal(id="alice", clearance="SECRET", org_unit="unit-1")
NOW = datetime(2026, 11, 8, tzinfo=UTC)


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"migrate_views_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


def _marked(dataset: str) -> NodeWrite:
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={"family_name": "MERCER", "given_names": "Dana"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="analyst:alice", locator="mark", excerpt_hash="")],
            first_seen=NOW,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        created_at=NOW,
        created_by="alice",
        datasets=[dataset],
    )


async def _seeded(dsn: str, graph: Any) -> dict[str, str]:
    """Kestrel with its layer; a case copied from it since L3.1 (the link); and one made before
    L3.1 holding a mark in a layer the old migration made."""
    investigations = await InvestigationStore.connect(dsn)
    datasets = await PostgresDatasetStore.connect(dsn)
    try:
        src = await datasets.create(ALICE, "Prison intel")
        kestrel = await investigations.create(ALICE, name="Kestrel")
        await datasets.set_for_case(kestrel.id, [src.id], ALICE, case_name="Kestrel")
        original_layer = await datasets.layer_of_case(kestrel.id)
        assert original_layer is not None
        copied = await investigations.create(ALICE, name="Branch of Kestrel")
        await made_before_l3_2_on_postgres(datasets, kestrel.id, copied.id)
        old = await investigations.create(ALICE, name="Old branch")
        old_layer = await datasets.ensure_layer(
            old.id, unit="unit-1", created_by=LEGACY_LAYER_MAKER, case_name="Old branch"
        )
        await datasets.set_for_case(old.id, [src.id], ALICE, case_name="Old branch")
    finally:
        await investigations.close()
        await datasets.close()
    # The origin column as a database from before L3.2 holds it; the store no longer writes it.
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "ALTER TABLE investigations ADD COLUMN branched_from TEXT REFERENCES investigations (id)"
        )
        await conn.execute(
            "UPDATE investigations SET branched_from = $1 WHERE id = ANY($2::text[])",
            kestrel.id,
            [copied.id, old.id],
        )
    finally:
        await conn.close()
    mark = _marked(old_layer)
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([mark], tx)
    await graph.commit_transaction(tx)
    return {"kestrel": kestrel.id, "copied": copied.id, "old": old.id, "mark": mark.id,
            "original_layer": original_layer, "old_layer": old_layer}  # fmt: skip


async def _rows(conn: asyncpg.Connection) -> Any:
    views = (
        await conn.fetch("SELECT * FROM case_views ORDER BY id")
        if await conn.fetchval("SELECT to_regclass('case_views') IS NOT NULL")
        else []
    )
    cases = await conn.fetch("SELECT id, branched_from, removed_at FROM investigations ORDER BY id")
    links = await conn.fetch("SELECT * FROM case_layer_reads ORDER BY investigation_id")
    return [dict(r) for r in cases], [dict(r) for r in links], [dict(r) for r in views]


async def _element(sql: _Sql, node_id: str) -> dict[str, Any]:
    person = physical_type_name("Person")
    query = f"SELECT datasets, {TAG} FROM {person} WHERE id = :id"
    (row,) = await sql.query(query, {"id": node_id})
    return dict(row)


async def test_the_dry_run_changes_nothing_and_the_real_run_converts_in_both_stores(
    dsn: str,
) -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        ids = await _seeded(dsn, graph)
        sql = _Sql(graph._client)  # noqa: SLF001 - the script's own SQL, on the test database
        types = _type_names(ONTOLOGY)
        working = FakeWorkingSetStore()
        await working.add_nodes(ids["copied"], [node("p1"), node("p2")])
        await working.set_threshold(ids["copied"], 0.7)
        conn = await asyncpg.connect(dsn)
        try:
            reads = DeploymentReads(conn, working, sql, types)  # type: ignore[arg-type]
            before_rows, before_mark = await _rows(conn), await _element(sql, ids["mark"])
            dry = Report()
            await migrate(reads, DryRun(reads, dry.writes), dry)
            assert await _rows(conn) == before_rows
            assert await _element(sql, ids["mark"]) == before_mark
            assert [c.moved for c in dry.converted] == [0, 1]

            views = await PostgresCaseViewStore.connect(dsn)
            try:
                real = Report()
                await migrate(reads, DeploymentWrites(conn, views, sql, types, real.writes), real)
                assert len(real.writes) == len(dry.writes)
                listed = await views.visible_in(ids["kestrel"], "alice")
            finally:
                await views.close()
            assert real.unplaced == []
            by_origin = {v.converted_from_case: v for v in listed}
            assert set(by_origin) == {ids["copied"], ids["old"]}
            assert by_origin[ids["copied"]].node_ids == ["p1", "p2"]
            assert by_origin[ids["copied"]].threshold == 0.7
            assert not any(v.shared for v in listed)
            cases, links, _ = await _rows(conn)
            for case in cases:
                assert case["branched_from"] is None
                if case["id"] in (ids["copied"], ids["old"]):
                    assert case["removed_at"] is not None
            assert links == []
            moved = await _element(sql, ids["mark"])
            held = moved["datasets"]
            held = json.loads(held) if isinstance(held, str) else list(held)
            assert held == [ids["original_layer"]]
            assert moved[TAG] == "Old branch"

            again = Report()
            await migrate(reads, DryRun(reads, again.writes), again)
            assert again.converted == [] and again.writes == []
        finally:
            await conn.close()
