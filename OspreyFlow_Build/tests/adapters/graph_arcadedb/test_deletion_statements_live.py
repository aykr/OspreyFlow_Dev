"""SE9c, on real ArcadeDB: the three statements that record a deletion run, and the rows read back
carry when and by whom (SE9, ADR-144 Amendment 7).

On `2e13b10` each of them named `:by`, which ArcadeDB's SQL refuses as a parameter name, and 80 live
tests failed on GitHub; no fake could say so. This is the proof against the database itself, one
case for each path, each over a node and a link: `revert_elements` (the deleting write),
`withdraw_elements` (the revert by load) and `withdraw_layer` (the dataset withdrawal). Each reads
the flag, `reverted_at` and `reverted_by` back, and the withdrawn-by-load marking the statement sets
or clears. The pure twin, which names the refused parameter names, is
`test_deletion_statement_parameters.py`.

Needs a live ArcadeDB (`make conformance` runs the directory): run alone with
`cd OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \
../OspreyFlow_Build/tests/adapters/graph_arcadedb/test_deletion_statements_live.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, NodeWrite, Provenance, ProvenanceState, SourceRef

pytestmark = pytest.mark.store  # reaches ArcadeDB (tests/store_mark.py)

ONTOLOGY = load_default_ontology()
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
AT = datetime(2026, 11, 24, 9, 30, tzinfo=UTC)
WHO = "analyst-1"
SOURCE = SourceRef(document_id="files/calls.csv", locator="row 3", excerpt_hash="d" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)


def _person(datasets: list[str]) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": "Quillfeather"},
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by=WHO,
        created_at=WHEN,
        datasets=datasets,
    )


async def _seed(graph, datasets: list[str]):  # type: ignore[no-untyped-def]
    """Two people and a link between them, each in `datasets`, committed."""
    a, b = _person(datasets), _person(datasets)
    link = EdgeWrite(
        id=new_edge_id(),
        type="ASSOCIATE_OF",
        source=a.id,
        target=b.id,
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by=WHO,
        created_at=WHEN,
        datasets=datasets,
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([a, b], tx)
    await graph.upsert_edges([link], tx)
    await graph.commit_transaction(tx)
    return a, b, link


async def _row(graph, table: str, element_id: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """The stored row, read through the base type (`V` for a node, `E` for a link): the deleting
    statements' own record, which no port read returns."""
    rows = await graph._client.sql(
        f"SELECT reverted, reverted_at, reverted_by, withdrawn_by_load FROM {table} WHERE id = :id",
        params={"id": element_id},
    )
    assert len(rows) == 1, f"{element_id} is stored once, in {table}"
    return rows[0]


def _recorded(row: dict[str, Any], withdrawn_by_load: str | None) -> None:
    assert row["reverted"] is True
    assert row["reverted_by"] == WHO
    assert row["reverted_at"] == AT.isoformat()
    assert row.get("withdrawn_by_load") == withdrawn_by_load


async def test_a_deleting_write_records_when_and_by_whom_and_clears_the_withdrawal() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, b, link = await _seed(graph, ["layer-1"])
        tx = await graph.begin_transaction()
        await graph.revert_elements([a.id], [link.id], tx, by=WHO, at=AT)
        await graph.commit_transaction(tx)

        _recorded(await _row(graph, "V", a.id), None)
        _recorded(await _row(graph, "E", link.id), None)
        untouched = await _row(graph, "V", b.id)
        assert untouched.get("reverted") in (None, False)
        assert untouched.get("reverted_by") is None


async def test_a_revert_by_load_records_when_and_by_whom_and_names_the_load() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, b, link = await _seed(graph, ["layer-1"])
        tx = await graph.begin_transaction()
        await graph.withdraw_elements([a.id], [link.id], "load-2", tx, by=WHO, at=AT)
        await graph.commit_transaction(tx)

        _recorded(await _row(graph, "V", a.id), "load-2")
        _recorded(await _row(graph, "E", link.id), "load-2")
        untouched = await _row(graph, "V", b.id)
        assert untouched.get("reverted") in (None, False)
        assert untouched.get("withdrawn_by_load") is None


async def test_a_dataset_withdrawal_records_when_and_by_whom_and_names_the_withdrawal() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, b, link = await _seed(graph, ["layer-1"])
        other = await _seed(graph, ["layer-2"])
        tx = await graph.begin_transaction()
        counts = await graph.withdraw_layer("layer-1", "layer-delete:case-a", tx, by=WHO, at=AT)
        await graph.commit_transaction(tx)

        assert (counts.nodes, counts.edges) == (2, 1)
        for node in (a, b):
            _recorded(await _row(graph, "V", node.id), "layer-delete:case-a")
        _recorded(await _row(graph, "E", link.id), "layer-delete:case-a")
        for kept in (other[0].id, other[1].id):
            assert (await _row(graph, "V", kept)).get("reverted") in (None, False)
