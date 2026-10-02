"""`BulkGraphLoader` conformance — `spec/04_VAULT_BACKEND.md` §6, ADR-058.

Written before any adapter builds the capability (rule 1). Parametrised over `GRAPH_PORT_ADAPTERS`
like `test_suite.py`; an adapter that does not declare `BulkGraphLoader` skips every case here, and
the Ingest Studio engine loads it through chunked `upsert_edges` instead (ADR-058 D1). Each case
names the invariant it guards (rule 12): the ones that matter most are validation parity with
`upsert_edges` (the loader is never trusted), a stored pair handed back rather than merged or
dropped, and weights taken against the corpus at the end of the load.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ontology.errors import OntologyError
from ports.graph import BulkGraphLoader, GraphPort
from schemas.domain import (
    EdgeWrite,
    ExpandRequest,
    Interval,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from tests.conformance.graph_port.test_suite import CLEARED, _edge, _node, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

pytestmark = [
    pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str),
    pytest.mark.usefixtures("_sweep_stale_conformance_databases"),
]

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def _loader(adapter: GraphPort) -> BulkGraphLoader:
    if not isinstance(adapter, BulkGraphLoader):
        pytest.skip(
            "this adapter does not declare BulkGraphLoader; the engine falls back to upsert"
        )
    return adapter


async def _endpoints(adapter: GraphPort, count: int) -> list[str]:
    nodes = [
        _node("Endpoint", classification="OFFICIAL", value_normalised=f"+44100000{n:04d}")
        for n in range(count)
    ]
    ids, _ = await _write(adapter, nodes, [])
    return ids


def _comm(source: str, target: str, *, occurrences: int = 1, row: str = "r1") -> EdgeWrite:
    write = _edge(
        "COMMUNICATED_WITH", source, target, classification="OFFICIAL", occurrences=occurrences
    )
    return write.model_copy(
        update={
            "provenance": Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[SourceRef(document_id="doc-bulk", locator=row, excerpt_hash="")],
                first_seen=T0,
            )
        }
    )


async def _edges_of(adapter: GraphPort, node: str) -> list:  # type: ignore[type-arg]
    return (await adapter.expand(ExpandRequest(node_ids=[node], depth=1), CLEARED)).edges


# --- one element and many ----------------------------------------------------


async def test_a_bulk_edge_reads_back_like_an_upserted_one(factory: GraphAdapterFactory) -> None:
    """Catches the bulk path storing an edge differently from `upsert_edges` for the same write:
    properties, interval, provenance, handling, occurrences and revision must match."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c, d = await _endpoints(adapter, 4)
        interval = Interval(valid_from=T0, valid_to=T0 + timedelta(minutes=5))
        props = {"duration_s": 42.5, "direction": "inbound"}
        bulk = _comm(a, b, occurrences=3).model_copy(
            update={"interval": interval, "properties": props}
        )
        upserted = _comm(c, d, occurrences=3).model_copy(
            update={"interval": interval, "properties": props}
        )
        result = await loader.bulk_load_edges([bulk])
        await _write(adapter, [], [upserted])

        assert result.written == [bulk.id] and result.collisions == [] and result.received == 1
        (from_bulk,) = await _edges_of(adapter, a)
        (from_upsert,) = await _edges_of(adapter, c)
        for field in ("properties", "interval", "occurrences", "handling"):
            assert getattr(from_bulk, field) == getattr(from_upsert, field), field
        assert from_bulk.provenance.sources == from_upsert.provenance.sources
        assert from_bulk.audit.revision == from_upsert.audit.revision == 1
        assert from_bulk.weight_components is not None
        assert from_bulk.weight_components.occurrences == 3


async def test_an_empty_call_does_nothing(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        result = await _loader(adapter).bulk_load_edges([])
        assert result.written == [] and result.collisions == [] and result.received == 0


# --- validation parity: the loader is never trusted --------------------------


@pytest.mark.parametrize("fault", ["unknown_type", "bad_property", "missing_endpoint", "bad_ends"])
async def test_a_bad_edge_raises_before_anything_is_written(
    factory: GraphAdapterFactory, fault: str
) -> None:
    """Catches the bulk path skipping `upsert_edges`' checks, or checking only as it goes: a batch
    with one bad edge among good ones must raise `OntologyError` and leave the graph untouched."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c = await _endpoints(adapter, 3)
        good = [_comm(a, b), _comm(b, c)]
        bad = {
            "unknown_type": _comm(a, c).model_copy(update={"type": "NOT_A_TYPE"}),
            "bad_property": _comm(a, c).model_copy(update={"properties": {"duration_s": "x"}}),
            "missing_endpoint": _comm(a, "no-such-node"),
            # USES runs from a Person, so an Endpoint cannot be its source.
            "bad_ends": _comm(a, c).model_copy(update={"type": "USES"}),
        }[fault]
        with pytest.raises(OntologyError):
            await loader.bulk_load_edges([*good, bad])
        assert await _edges_of(adapter, a) == []
        assert await _edges_of(adapter, b) == []


# --- aggregating, and the pair that already exists ---------------------------


async def test_repeated_pairs_in_one_call_become_one_edge_with_everything_kept(
    factory: GraphAdapterFactory,
) -> None:
    """Catches a pair being stored twice, or losing a source row or occurrence, when it recurs in
    one call: the result must be what the same writes through `upsert_edges` would have left."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b = await _endpoints(adapter, 2)
        writes = [
            _comm(a, b, occurrences=2, row="r1"),
            _comm(a, b, occurrences=5, row="r2"),
            _comm(a, b, occurrences=1, row="r3"),
        ]
        result = await loader.bulk_load_edges(writes)

        assert result.written == [writes[0].id] and result.received == 3
        (edge,) = await _edges_of(adapter, a)
        assert edge.id == writes[0].id and edge.occurrences == 8
        assert [s.locator for s in edge.provenance.sources] == ["r1", "r2", "r3"]
        assert edge.audit.revision == 3


async def test_a_stored_pair_is_handed_back_not_written_or_merged(
    factory: GraphAdapterFactory,
) -> None:
    """Catches the bulk path merging into, overwriting or silently dropping a pair that is already
    stored: it must come back in `collisions`, the stored edge must be untouched, and routing the
    collision through `upsert_edges` must then merge as it always has."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c, d = await _endpoints(adapter, 4)
        await _write(adapter, [], [_comm(a, b, occurrences=3, row="stored")])

        fresh = _comm(c, d, occurrences=1, row="fresh")
        clash = _comm(a, b, occurrences=2, row="clash")
        result = await loader.bulk_load_edges([clash, fresh])

        assert result.written == [fresh.id]
        assert [(x.source, x.target, x.occurrences) for x in result.collisions] == [(a, b, 2)]
        (stored,) = await _edges_of(adapter, a)
        assert stored.occurrences == 3  # untouched

        tx = await adapter.begin_transaction()
        await adapter.upsert_edges(result.collisions, tx)
        await adapter.commit_transaction(tx)
        (merged,) = await _edges_of(adapter, a)
        assert merged.occurrences == 5
        assert [s.locator for s in merged.provenance.sources] == ["stored", "clash"]


async def test_a_reverted_pair_is_not_a_collision(factory: GraphAdapterFactory) -> None:
    """Catches a retracted edge blocking a fresh one for the same pair: `upsert_edges` starts a
    fresh edge rather than resurrecting retracted data, and the bulk path must too."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b = await _endpoints(adapter, 2)
        _, (old_id,) = await _write(adapter, [], [_comm(a, b, occurrences=9, row="old")])
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([], [old_id], tx)
        await adapter.commit_transaction(tx)

        new = _comm(a, b, occurrences=1, row="new")
        result = await loader.bulk_load_edges([new])
        assert result.written == [new.id] and result.collisions == []
        (edge,) = await _edges_of(adapter, a)
        assert edge.id == new.id and edge.occurrences == 1


# --- weights at the end of the load ------------------------------------------


async def test_weight_components_are_the_end_of_load_corpus(factory: GraphAdapterFactory) -> None:
    """Catches weights computed against a partial corpus, as a write-by-write load would: every edge
    of the call must carry the same corpus total (the whole call's occurrences) and each endpoint's
    degree over the whole call, whatever the order or chunking."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c, d = await _endpoints(adapter, 4)
        ab, ac, db = (
            _comm(a, b, occurrences=1),
            _comm(a, c, occurrences=2),
            _comm(d, b, occurrences=4),
        )
        await loader.bulk_load_edges([ab, ac, db], chunk_size=1)

        by_pair = {(e.source, e.target): e for e in await _edges_of(adapter, a)}
        by_pair.update({(e.source, e.target): e for e in await _edges_of(adapter, d)})
        expected = {  # (source degree, target degree), over occurrences touching each end
            (a, b): (3, 5),
            (a, c): (3, 2),
            (d, b): (4, 5),
        }
        for pair, (source_degree, target_degree) in expected.items():
            components = by_pair[pair].weight_components
            assert components is not None
            assert components.corpus_total_occurrences == 7
            assert components.corpus_source_degree == source_degree
            assert components.corpus_target_degree == target_degree
            assert components.corpus_pair_count == components.occurrences


async def test_what_is_already_stored_is_part_of_the_end_of_load_corpus(
    factory: GraphAdapterFactory,
) -> None:
    """Catches the load's weights ignoring edges already in the vault: the corpus total and the
    degrees of a node the load touches must include what was there before it."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c = await _endpoints(adapter, 3)
        await _write(adapter, [], [_comm(a, b, occurrences=10, row="before")])
        await loader.bulk_load_edges([_comm(a, c, occurrences=2)])

        new = next(e for e in await _edges_of(adapter, c))
        assert new.weight_components is not None
        assert new.weight_components.corpus_total_occurrences == 12
        assert new.weight_components.corpus_source_degree == 12  # a: 10 stored + 2 loaded
        assert new.weight_components.corpus_target_degree == 2


# --- chunking, progress, and revert ------------------------------------------


async def test_chunk_size_does_not_change_what_is_stored(factory: GraphAdapterFactory) -> None:
    """Catches the result depending on how the call was cut into transactions."""
    snapshots = []
    for chunk in (1, 500):
        async with factory.context() as adapter:
            loader = _loader(adapter)
            nodes = await _endpoints(adapter, 6)
            writes = [_comm(nodes[i], nodes[i + 1], occurrences=i + 1) for i in range(5)]
            await loader.bulk_load_edges(writes, chunk_size=chunk)
            seen = {}
            for node in nodes:
                for e in await _edges_of(adapter, node):
                    components = e.weight_components
                    assert components is not None
                    seen[(nodes.index(e.source), nodes.index(e.target))] = (
                        e.occurrences,
                        components.corpus_total_occurrences,
                        components.corpus_source_degree,
                        components.corpus_target_degree,
                    )
            snapshots.append(seen)
    assert snapshots[0] == snapshots[1] and len(snapshots[0]) == 5


async def test_progress_is_reported_after_each_chunk(factory: GraphAdapterFactory) -> None:
    async with factory.context() as adapter:
        loader = _loader(adapter)
        nodes = await _endpoints(adapter, 5)
        writes = [_comm(nodes[i], nodes[i + 1]) for i in range(4)]
        seen: list[tuple[int, int]] = []
        result = await loader.bulk_load_edges(
            writes, chunk_size=2, progress=lambda done, total: seen.append((done, total))
        )
        assert seen == [(2, 4), (4, 4)] and result.chunks == 2


async def test_reverting_what_a_load_wrote_leaves_the_rest_alone(
    factory: GraphAdapterFactory,
) -> None:
    """Catches a bulk-written edge that `revert_elements` cannot remove, or one that takes
    other edges with it: revert by id is how a failed load is cleared (ADR-058 D6)."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c, d = await _endpoints(adapter, 4)
        _, (kept_id,) = await _write(adapter, [], [_comm(a, b, row="kept")])
        written = [_comm(c, d, row="bulk")]
        result = await loader.bulk_load_edges(written)
        tx = await adapter.begin_transaction()
        await adapter.revert_elements([], result.written, tx)
        await adapter.commit_transaction(tx)
        assert await _edges_of(adapter, c) == []
        assert [e.id for e in await _edges_of(adapter, a)] == [kept_id]
