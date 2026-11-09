"""The grading change through the command itself, against the real stores (ADR-143 decision 11 and
Amendment 6; the owner's ruling C13; L3.7; rule 15's second worked example: the offline tests run
over a fake, so the whole command is also proved against what it really meets).

**Live, against a lane's leased stack** (`scripts/stack_lease.sh`): a throwaway ArcadeDB database
(`conformance_*`) and a throwaway Postgres database (`grading_*`), both dropped afterwards. It runs
`scripts.grading_change._main` as the deployment runs it, in a process with no ontology applied
and no link-type aliases set, as a one-shot starts: its own registry read, its own `AuditWriter`,
its own bare adapter. What is changed: two drawn people, a drawn link between them of an analyst's
proposed link type (L3.5, stored under its own storage label), and a drawn `ASSOCIATE_OF` link
counted three times; then all four back again, each keeping the original it was drawn with.

What a mistake would do, and the case that catches it:
- a proposed type's link not read by the command; its dry run writing, or making a table; the change without the dry run's token; a rewrite that loses the item's marking,
  datasets, properties, resolution state or the rest of its assertion, counts a link again or
  weighs it again; no audit record, or a record of who changed it that does not say it is as typed:
  `test_the_command_changes_every_drawn_grade_in_the_real_stores`.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest
from adapters.graph_arcadedb import naming
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_id, new_node_id
from ontology.handling import load_uk_le_scheme, sources_in_full
from ontology.packs import load_deployment_ontology
from scripts import grading_change
from services.api.board_store import PostgresBoardItemStore, new_item
from services.api.config import PostgresConfig
from services.api.grading import operator_reader
from services.api.link_type_store import LinkTypeProposalStore
from services.api.link_types import LinkTypeProposal, compose_ontology

from schemas.domain import (
    DrawnAssertion,
    EdgeWrite,
    Grading,
    Handling,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

UNIT = "unit-1"
K = "case-k"
LAYER = "layer-k"

#: As `tests/harness/test_restore_drawn_layer.py`'s: a leased lane stack, or CI's live job.
pytestmark = pytest.mark.skipif(
    not os.environ.get("OSPREY_LANE") and not os.environ.get("OSPREY_TEST_ARCADEDB_CONTAINER"),
    reason="needs a leased lane stack (OSPREY_LANE and its pinned ports), or CI's live job",
)

THREE_TO_FIVE = """
from: 3x5x2
to: 5x5x5
source: {A: A, B: C, C: E}
intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
handling: {P: "1", C: "4"}
"""

FIVE_TO_THREE = """
from: 5x5x5
to: 3x5x2
source: {A: A, B: A, C: B, D: C, E: C}
intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
handling: {"1": P, "2": P, "3": P, "4": C, "5": C}
"""


@pytest.fixture
async def stores(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    """A Postgres database and an ArcadeDB database of their own, the command pointed at both."""
    base = PostgresConfig.from_env()
    database = f"grading_{new_id().lower()}"
    admin = await asyncpg.connect(base.dsn)
    await admin.execute(f'CREATE DATABASE "{database}"')
    monkeypatch.setenv("POSTGRES_DB", database)
    monkeypatch.delenv("OSPREY_GRADING_SCHEME", raising=False)
    monkeypatch.delenv("OSPREY_GRADING_GRADES", raising=False)
    dsn = PostgresConfig.from_env().dsn
    proposals = registry = None
    try:
        proposals = await LinkTypeProposalStore.connect(dsn)
        registry = await PostgresBoardItemStore.connect(dsn)
        proposal = LinkTypeProposal(
            id=new_id(), name="SHARED_CELL_WITH", from_types=["Person"], to_types=["Person"],
            investigation_id=K, owning_unit=UNIT, proposed_by="alice",
            proposed_at=datetime.now(UTC), reason="seen together on the wing",
        )  # fmt: skip
        await proposals.create(proposal)
        ontology = compose_ontology(
            load_deployment_ontology(), [proposal], revision=await proposals.revision()
        )
        scheme = load_uk_le_scheme()
        async with arcadedb_adapter(ontology, scheme) as adapter:
            monkeypatch.setenv("ARCADEDB_DATABASE", adapter._client.database)
            yield SimpleNamespace(
                adapter=adapter, registry=registry, proposal=proposal, dsn=dsn,
                reader=operator_reader(scheme, org_unit=UNIT),
            )  # fmt: skip
    finally:
        for store in (proposals, registry):
            if store is not None:
                await store.close()
        await admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        await admin.close()


def _drawn(grade: Grading, item: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id=f"drawn:{item}", locator="drawn", excerpt_hash="")],
        first_seen=datetime.now(UTC),
        drawn=DrawnAssertion(item_id=item, asserted_by="alice", board_id="board-1", case_id=K,
                             label=item, grading=grade, source_note="Wing officer report"),
    )  # fmt: skip


async def _draw(world: SimpleNamespace) -> dict[str, str]:
    """Two people and two links between them, written as a board writes them, and registered."""
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator=UNIT, owning_unit=UNIT
    )
    now = datetime.now(UTC)
    graded = Grading(source="B", intelligence="2", handling="1")
    ids = {"tall": new_node_id(), "short": new_node_id()}
    tx = await world.adapter.begin_transaction()
    await world.adapter.upsert_nodes(
        [NodeWrite(id=ids[n], type="Person", properties={"family_name": n}, handling=handling,
                   provenance=_drawn(graded, f"item-{n}"), created_by="alice", created_at=now,
                   datasets=[LAYER]) for n in ("tall", "short")],
        tx,
    )  # fmt: skip
    proposed, associate = await world.adapter.upsert_edges(
        [EdgeWrite(id=new_edge_id(), type=t, source=ids["tall"], target=ids["short"],
                   handling=handling, provenance=_drawn(graded, f"item-{t}"), occurrences=o,
                   created_by="alice", created_at=now, datasets=[LAYER])
         for t, o in ((world.proposal.storage_name, 1), ("ASSOCIATE_OF", 3))],
        tx,
    )  # fmt: skip
    await world.adapter.commit_transaction(tx)
    ids |= {"proposed": proposed, "associate": associate}
    for name, kind in (("tall", "node"), ("short", "node"), ("proposed", "link"),
                       ("associate", "link")):  # fmt: skip
        await world.registry.add(
            new_item(board_id="board-1", case_id=K, kind=kind, element_id=ids[name],
                     author="alice", dataset_id=LAYER),
            None,
        )  # fmt: skip
    # A resolution state of the person's own, which a rewrite writing a fresh one would lose.
    (held,) = await world.adapter._holders("vertex", [ids["tall"]])
    await world.adapter._client.sql(
        f"UPDATE `{held[0]}` SET resolution = :r WHERE id = :id",
        params={"r": {"cluster_id": "cl-1", "cluster_score": 0.9, "resolution_run": None,
                      "manually_linked": [], "manually_split": []}, "id": ids["tall"]},
    )  # fmt: skip
    return ids


async def _stored(world: SimpleNamespace, ids: dict[str, str]) -> dict[str, Any]:
    with sources_in_full():
        nodes = await world.adapter.get_nodes([ids["tall"], ids["short"]], world.reader)
        edges = await world.adapter.get_edges([ids["proposed"], ids["associate"]], world.reader)
    return {e.id: e for e in [*nodes, *edges]}


def _kept(element: Any) -> Any:
    """Everything of the element but its drawn grade and original."""
    dumped = element.model_dump(exclude={"provenance"})
    drawn = element.provenance.drawn.model_dump(exclude={"grading", "original_grading"})
    return dumped, drawn, element.provenance.model_dump(exclude={"drawn"})


async def _tables(dsn: str) -> set[str]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    finally:
        await conn.close()
    return {r["tablename"] for r in rows}


async def test_the_command_changes_every_drawn_grade_in_the_real_stores(
    stores: SimpleNamespace, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    ids = await _draw(stores)
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(FIVE_TO_THREE, encoding="utf-8")

    async def quiet(_: str) -> bool:
        return False

    async def main(*more: str, to: str = "3x5x2", mapping_file: Any = mapping) -> int:
        args = grading_change.build_parser().parse_args(
            ["--to", to, "--mapping", str(mapping_file), "--changed-by", "cli:operator", *more]
        )
        # As a one-shot process starts: no ontology applied, so no link-type aliases set.
        held = (dict(naming._CANONICAL), dict(naming._ALIASES_OF))
        naming.set_edge_aliases({})
        try:
            return await grading_change._main(args, answers=quiet)
        finally:
            naming._CANONICAL.update(held[0])
            naming._ALIASES_OF.update(held[1])

    before = await _stored(stores, ids)
    assert len(before) == 4
    assert before[ids["proposed"]].type == "SHARED_CELL_WITH"  # read under its name
    tables = await _tables(stores.dsn)

    assert await main("--dry-run") == 0
    said = capsys.readouterr().out
    assert "5x5x5 to 3x5x2: 4 item(s) to change." in said, said
    token = said.strip().rsplit(" ", 1)[-1]
    assert await _stored(stores, ids) == before, "a dry run writes nothing"
    assert await _tables(stores.dsn) == tables, "a dry run makes no table"

    assert await main("--confirm", "not-the-token") == 1
    assert "a dry run of this mapping" in capsys.readouterr().out
    assert await _stored(stores, ids) == before

    assert await main("--confirm", token) == 0
    assert "Changed 4 item(s) to 3x5x2" in capsys.readouterr().out
    after = await _stored(stores, ids)
    original = Grading(source="B", intelligence="2", handling="1")
    for element_id, was in before.items():
        now = after[element_id]
        assert now.provenance.drawn.grading == Grading(
            scheme="3x5x2", source="A", intelligence="2", handling="P"
        ), element_id
        assert now.provenance.drawn.original_grading == original, element_id
        assert _kept(now) == _kept(was), element_id
    assert after[ids["tall"]].resolution.cluster_id == "cl-1"
    assert after[ids["associate"]].occurrences == 3
    assert after[ids["associate"]].weight == before[ids["associate"]].weight

    conn = await asyncpg.connect(stores.dsn)
    try:
        audited = await conn.fetch(
            "SELECT principal_id, resolved_query FROM audit_log WHERE action = 'grading_change' "
            "ORDER BY id"
        )
    finally:
        await conn.close()
    records = [
        json.loads(r["resolved_query"]) if isinstance(r["resolved_query"], str)
        else r["resolved_query"]
        for r in audited
    ]  # fmt: skip
    assert [r["stage"] for r in records] == ["started", "finished"]
    assert records[-1]["written"] == 4 and records[-1]["dry_run_token"] == token
    assert all(r["changed_by_as_typed"] is True for r in records)
    assert {r["principal_id"] for r in audited} == {"cli:operator"}

    # And back: the original is the grade drawn, never the middle one.
    back = tmp_path / "back.yaml"
    back.write_text(THREE_TO_FIVE, encoding="utf-8")
    os.environ["OSPREY_GRADING_SCHEME"] = "3x5x2"  # the setting the verb writes after a change
    try:
        assert await main("--dry-run", to="5x5x5", mapping_file=back) == 0
        token = capsys.readouterr().out.strip().rsplit(" ", 1)[-1]
        assert await main("--confirm", token, to="5x5x5", mapping_file=back) == 0
    finally:
        del os.environ["OSPREY_GRADING_SCHEME"]
    again = await _stored(stores, ids)
    for element_id, was in before.items():
        assert again[element_id].provenance.drawn.grading == Grading(
            source="A", intelligence="2", handling="1"
        ), element_id
        assert again[element_id].provenance.drawn.original_grading == original, element_id
        assert _kept(again[element_id]) == _kept(was), element_id
