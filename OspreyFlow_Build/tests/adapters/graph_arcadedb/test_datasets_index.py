"""Every graph type indexes `datasets` by item (ADR-099 decision 2, Amendment 6), and the index
answers what a scan answers, on real ArcadeDB.

What a mistake would do, and the case that catches it: a type with no index, so a read by dataset
scans it (`test_every_type_indexes_its_datasets_by_item`); an index that misses an element whose
datasets grew on a rewrite, which is the in-place change 25.5.1's indexes lost records on
(`test_the_index_and_a_scan_agree_after_a_rewrite_adds_a_dataset`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

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


# --- ADR-127 decision 11: no stale flattened end on a link a merge leaves open ---


def _endpoint(value: str) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Endpoint",
        properties={"value_normalised": value},
        provenance=PROVENANCE,
        handling=HANDLING,  # type: ignore[arg-type]
        created_by="t",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _span(source: str, target: str, interval: Interval) -> EdgeWrite:
    return EdgeWrite(
        id=new_edge_id(),
        type="COMMUNICATED_WITH",
        source=source,
        target=target,
        interval=interval,
        provenance=PROVENANCE,
        handling=Handling(**HANDLING),
        created_by="t",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_a_merge_that_leaves_a_span_open_leaves_no_flattened_end_in_the_store() -> None:
    """The stored link keeps its interval nested and its ends flattened (the flattened end only when
    there is one). A closed link merged with an open write must lose the flattened `valid_to` the
    closed write left, in the store itself: it reads back open, and the raw record has no end. A
    merge that stays closed keeps it."""
    start = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        tx = await graph.begin_transaction()
        a, b, c, d = await graph.upsert_nodes(
            [_endpoint(f"+44100000{n:04d}") for n in range(4)], tx
        )
        await graph.commit_transaction(tx)
        label = physical_type_name("COMMUNICATED_WITH")

        async def raw(source: str) -> dict[str, object]:
            (row,) = await graph._client.sql(  # noqa: SLF001
                f"SELECT valid_to, interval FROM `{label}` WHERE source = :s", params={"s": source}
            )
            return row

        async def write(edge: EdgeWrite) -> None:
            transaction = await graph.begin_transaction()
            await graph.upsert_edges([edge], transaction)
            await graph.commit_transaction(transaction)

        closed = Interval(valid_from=start, valid_to=start + timedelta(days=8))
        await write(_span(a, b, closed))
        assert (await raw(a))["valid_to"] is not None
        await write(_span(a, b, Interval(valid_from=start + timedelta(days=2), valid_to=None)))
        row = await raw(a)
        assert row["valid_to"] is None, "the closed write's end is left behind on an open link"
        assert row["interval"]["valid_to"] is None  # type: ignore[index]

        await write(_span(c, d, closed))
        await write(_span(c, d, Interval(valid_from=start, valid_to=start + timedelta(days=3))))
        assert (await raw(c))["valid_to"] is not None, "a merge that stays closed keeps its end"


async def test_the_operator_script_closes_only_old_paysim_instants() -> None:
    """`scripts.close_paysim_instants` on real ArcadeDB (ADR-127 decision 11): of the endless links,
    only a `TRANSACTED` link whose every source is `paysim-dataset`, written before the cutoff and
    not changed by an analyst, is closed at its start (nested interval and flattened end). Left
    open: a PaySim link written after the cutoff, a PaySim link an analyst changed, another source's
    `TRANSACTED`, an open span of another link type (as the PID's custody links are), and a
    reverted one. A dry run writes nothing; a rerun
    closes nothing."""
    from scripts.close_paysim_instants import close_paysim_instants

    start = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    cutoff = datetime(2026, 3, 1, tzinfo=UTC)
    long_ago, later = datetime(2026, 1, 5, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)
    open_span = Interval(valid_from=start, valid_to=None)
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        tx = await graph.begin_transaction()
        ends = await graph.upsert_nodes([_endpoint(f"+44200000{n:04d}") for n in range(12)], tx)
        await graph.commit_transaction(tx)
        pairs = [(ends[i], ends[i + 1]) for i in range(0, 12, 2)]
        paysim_old, paysim_new, changed, other, reverted, other_type = pairs

        def link(kind: str, pair: tuple[str, str], source: str, when: datetime) -> EdgeWrite:
            made = _span(*pair, open_span).model_copy(update={"type": kind, "created_at": when})
            return made.model_copy(
                update={
                    "provenance": made.provenance.model_copy(
                        update={
                            "sources": [
                                SourceRef(document_id=source, locator="row 1", excerpt_hash="")
                            ]
                        }
                    )
                }
            )

        writes = [
            link("TRANSACTED", paysim_old, "paysim-dataset", long_ago),
            link("TRANSACTED", paysim_new, "paysim-dataset", later),
            link("TRANSACTED", changed, "paysim-dataset", long_ago),
            link("TRANSACTED", other, "aml_transactions.csv", long_ago),
            link("TRANSACTED", reverted, "paysim-dataset", long_ago),
            # An open span of another link type (the PID's custody links are open on purpose; their
            # pack is not in the default ontology, so a type that is stands in), whatever its source.
            link("COMMUNICATED_WITH", other_type, "paysim-dataset", long_ago),
        ]
        transaction = await graph.begin_transaction()
        ids = await graph.upsert_edges(writes, transaction)
        await graph.commit_transaction(transaction)
        transaction = await graph.begin_transaction()
        await graph.revert_elements([], [ids[4]], transaction)
        await graph.commit_transaction(transaction)
        async def raw(source: str, kind: str = "TRANSACTED") -> dict[str, object]:
            (row,) = await graph._client.sql(  # noqa: SLF001
                f"SELECT valid_to, interval FROM `{physical_type_name(kind)}` WHERE source = :s",
                params={"s": source},
            )
            return row

        def ended(row: dict[str, object]) -> bool:
            return row["valid_to"] is not None and row["interval"]["valid_to"] is not None  # type: ignore[index]

        client = graph._client  # noqa: SLF001
        changed_ids = {ids[2]}
        dry = await close_paysim_instants(
            client, cutoff=cutoff, dry_run=True, ontology=ONTOLOGY, changed_link_ids=changed_ids
        )
        assert dry.closed == 1 and dry.left_open_after_cutoff == 1
        assert dry.left_open_changed_by_an_analyst == 1
        assert not ended(await raw(paysim_old[0])), "a dry run writes nothing"

        done = await close_paysim_instants(
            client, cutoff=cutoff, dry_run=False, ontology=ONTOLOGY, changed_link_ids=changed_ids
        )
        assert done.closed == 1
        row = await raw(paysim_old[0])
        assert ended(row)
        assert row["interval"]["valid_to"] == row["interval"]["valid_from"]  # type: ignore[index]
        for untouched in (paysim_new, changed, other, reverted):
            assert not ended(await raw(untouched[0])), untouched
        assert not ended(await raw(other_type[0], "COMMUNICATED_WITH")), "another link type"

        again = await close_paysim_instants(
            client, cutoff=cutoff, dry_run=False, ontology=ONTOLOGY, changed_link_ids=changed_ids
        )
        assert again.closed == 0
