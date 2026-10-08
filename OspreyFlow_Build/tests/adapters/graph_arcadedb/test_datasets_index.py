"""Every graph type indexes `datasets` by item (ADR-099 decision 2, Amendment 6), and the index
answers what a scan answers, on real ArcadeDB.

What a mistake would do, and the case that catches it: a type with no index, so a read by dataset
scans it (`test_every_type_indexes_its_datasets_by_item`); an index that misses an element whose
datasets grew on a rewrite, which is the in-place change 25.5.1's indexes lost records on
(`test_the_index_and_a_scan_agree_after_a_rewrite_adds_a_dataset`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import NodeWrite, Provenance, ProvenanceState, SourceRef

ONTOLOGY = load_default_ontology()
PROVENANCE = Provenance(
    state=ProvenanceState.ASSERTED,
    sources=[SourceRef(document_id="d", locator="p.1", excerpt_hash="a" * 64)],
    first_seen=datetime(2026, 1, 1, tzinfo=UTC),
)
HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "u",
    "owning_unit": "u",
}


def _person(datasets: list[str]) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": "X"},
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        created_by="t",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        datasets=datasets,
    )


async def test_every_type_indexes_its_datasets_by_item() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        rows = await graph._client.sql("SELECT name, typeName, properties FROM schema:indexes")  # noqa: SLF001
        indexed = {r["typeName"] for r in rows if "datasets" in str(r["properties"])}
        wanted = {
            physical_type_name(t.name) for t in (*ONTOLOGY.entity_types, *ONTOLOGY.edge_types)
        }
        assert wanted - indexed == set()


async def test_the_index_and_a_scan_agree_after_a_rewrite_adds_a_dataset() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        people = [_person(["enron"]), _person(["enron"]), _person(["fixture"])]
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(people, tx)
        await graph.commit_transaction(tx)
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([people[0].model_copy(update={"datasets": ["fixture"]})], tx)
        await graph.commit_transaction(tx)
        sql = graph._client.sql  # noqa: SLF001
        every = await sql("SELECT id, datasets FROM mx_Person")
        for dataset, want in (("enron", 2), ("fixture", 2)):
            found = await sql(f"SELECT id FROM mx_Person WHERE datasets CONTAINS '{dataset}'")
            by_scan = {r["id"] for r in every if dataset in (r["datasets"] or [])}
            assert {r["id"] for r in found} == by_scan and len(by_scan) == want, dataset
        # The plan is outside `result`, which the client returns alone, so it is read whole.
        client = graph._client  # noqa: SLF001
        response = await client._http.post(  # noqa: SLF001
            f"/api/v1/command/{client.database}",
            json={
                "language": "sql",
                "command": "EXPLAIN SELECT FROM mx_Person WHERE datasets CONTAINS 'enron'",
            },
        )
        assert "FETCH FROM INDEX" in response.json()["explain"]
