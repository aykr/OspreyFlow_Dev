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
from typing import Any

import pytest
from ontology.errors import OntologyError
from ports.graph import BulkGraphLoader, GraphPort
from schemas.domain import (
    Edge,
    EdgeWrite,
    ExpandRequest,
    Interval,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from tests.adapters.graph_arcadedb.edge_store import without_clock
from tests.conformance.graph_port.test_suite import (
    ALL_CASES,
    CLEARED,
    HIDING_CASES,
    LOOP_OCCURRENCES,
    _link_k,
    _pin_now,
    OTHER_OCCURRENCES,
    _edge,
    _node,
    _links_among,
    _past_interval,
    _use_weights_version,
    _write,
    two_store_weights,
)
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


async def test_a_bulk_open_span_reads_back_open_like_an_upserted_one(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-127 decision 11 on the bulk path: a link with no end (a span still running) is stored
    without one and reads back with `valid_to` of `None`, as the ordinary path reads it, and a
    repeated pair with an open write among its closed ones aggregates to open."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c, d, e, f = await _endpoints(adapter, 6)
        open_span = Interval(valid_from=T0, valid_to=None)
        closed = Interval(valid_from=T0 - timedelta(days=2), valid_to=T0 + timedelta(minutes=5))
        bulk = _comm(a, b, occurrences=1).model_copy(update={"interval": open_span})
        upserted = _comm(c, d, occurrences=1).model_copy(update={"interval": open_span})
        await loader.bulk_load_edges([bulk])
        await _write(adapter, [], [upserted])
        (from_bulk,) = await _edges_of(adapter, a)
        (from_upsert,) = await _edges_of(adapter, c)
        assert from_bulk.interval == from_upsert.interval == open_span

        pair = [
            _comm(e, f, occurrences=1).model_copy(update={"interval": closed}),
            _comm(e, f, occurrences=1).model_copy(update={"interval": open_span}),
        ]
        await loader.bulk_load_edges(pair)
        (merged,) = await _edges_of(adapter, e)
        assert merged.interval == Interval(valid_from=T0 - timedelta(days=2), valid_to=None)


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


async def test_a_bulk_load_of_two_datasets_writes_two_links_each_case_reads_only_its_own(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-102 Amendment 3 overturns ADR-099's "one link in both datasets" for a pair that recurs in
    one load across two datasets: the set of datasets is part of the audience, so the loader writes
    two links, as two `upsert_edges` calls would leave them. A case of either reads its own, with
    only its own dataset on it, and a case of neither reads none."""
    from tests.conformance.graph_port.test_suite import IN_ENRON, IN_FIXTURE

    async with factory.context() as adapter:
        loader = _loader(adapter)
        nodes = [
            _node(
                "Endpoint",
                classification="OFFICIAL",
                datasets=["enron", "fixture"],
                value_normalised=f"+44200000{n:04d}",
            )
            for n in range(2)
        ]
        (a, b), _ = await _write(adapter, nodes, [])
        writes = [
            _comm(a, b, row="r1").model_copy(update={"datasets": ["fixture"]}),
            _comm(a, b, row="r2").model_copy(update={"datasets": ["enron"]}),
        ]
        result = await loader.bulk_load_edges(writes)
        assert sorted(result.written) == sorted(w.id for w in writes)
        assert sorted(tuple(e.datasets) for e in await _edges_of(adapter, a)) == [
            ("enron",),
            ("fixture",),
        ]
        (in_fixture,) = await adapter.edges_among([a, b], IN_FIXTURE)
        (in_enron,) = await adapter.edges_among([a, b], IN_ENRON)
        assert in_fixture.datasets == ["fixture"] and in_enron.datasets == ["enron"]
        elsewhere = IN_ENRON.model_copy(update={"datasets": ["paysim"]})
        assert await adapter.edges_among([a, b], elsewhere) == []


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


async def test_a_superseded_link_is_not_in_the_end_of_load_corpus(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-120 Amendment 5, decision 1, on the bulk path. Violated by a bulk transport whose degree
    and total queries filter only `reverted`: a link a -> b stored at 5 and superseded by one at 2,
    then a -> c bulk-loaded at 4, leaves the loaded link a degree at `a` of 5 + 2 + 4 = 11 and a
    type total of 11, where reads (and the upsert path) give 2 + 4 = 6 for both."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c = await _endpoints(adapter, 3)
        _, (old,) = await _write(adapter, [], [_comm(a, b, occurrences=5, row="old")])
        tx = await adapter.begin_transaction()
        await adapter.supersede_edge(old, _comm(a, b, occurrences=2, row="new"), tx)
        await adapter.commit_transaction(tx)

        await loader.bulk_load_edges([_comm(a, c, occurrences=4, row="bulk")])

        (loaded,) = await _edges_of(adapter, c)
        assert loaded.weight_components is not None
        assert loaded.weight_components.corpus_source_degree == 2 + 4
        assert loaded.weight_components.corpus_target_degree == 4
        assert loaded.weight_components.corpus_total_occurrences == 2 + 4


@pytest.mark.parametrize("weights_version", [1, 2, 3])
async def test_the_bulk_loader_stamps_the_same_parameter_set_as_an_upsert(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, weights_version: int
) -> None:
    """ADR-120 D3 and Amendment 4: the bulk path and `upsert_edges` weigh with the same rules, so
    a stored link has the same parameter set, components and weight whichever wrote it. Catches the
    bulk loader storing no parameter set, the default rule's name for a type that has its own, a
    structural type's weight that is not its strength, an unlisted type that does not take the
    default rule, a self-loop counted once in its node's degree or given a mutual-information term,
    and a weight taken at a recency of 1 for a link that ended in the past. A counted type, a
    self-loop of it (at a node with other occurrences), a structural type and an unlisted type,
    each written once by each path.

    ADR-123: run under versions 1 and 2, and under version 3 (ADR-120 Amendment 9 decision 9), each
    pinned by index and handed to the adapter (`_use_weights_version`), not "latest". The
    mutual-information term is zero from version 2, so a path that gave the self-loop one can be
    seen only under version 1, which is why that version stays in the matrix. The unlisted type is
    `ASSOCIATE_OF`, which has no rule in any version: `USES` took the default rule until version 3
    gave it a fixed one, so a case that names `USES` as unlisted would be wrong under version 3."""
    from ontology.weights import load_weight_history

    from adapters.graph_arcadedb.weight import compute_weight

    rules = load_weight_history()[weights_version - 1]
    assert rules.version == weights_version
    _use_weights_version(monkeypatch, weights_version)
    interval = _past_interval()

    async def write(adapter: GraphPort, *, bulk: bool) -> dict[str, Edge]:
        """The same links written into a fresh database by one path, read back by label (the
        self-loop through `edges_among`: `expand` cannot return one)."""
        (a, b), _ = await _write(
            adapter,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
            ],
            [],
        )
        (p, q), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL") for _ in range(2)], []
        )
        links = [
            _edge(
                "COMMUNICATED_WITH",
                a,
                b,
                classification="OFFICIAL",
                occurrences=OTHER_OCCURRENCES,
                interval=interval,
            ),
            _edge("FAMILY_OF", p, q, classification="OFFICIAL", occurrences=2, interval=interval),
            _edge(
                "ASSOCIATE_OF", p, q, classification="OFFICIAL", occurrences=3, interval=interval
            ),
        ]
        loop = _edge(
            "COMMUNICATED_WITH",
            a,
            a,
            classification="OFFICIAL",
            occurrences=LOOP_OCCURRENCES,
            interval=interval,
        )
        if bulk:
            await _loader(adapter).bulk_load_edges([*links, loop])
        else:
            await _write(adapter, [], links)
            await _write(adapter, [], [loop])
        found: dict[str, Edge] = {}
        for edge in await _links_among(adapter, [a, b, p, q]):
            found["SELF_LOOP" if edge.source == edge.target else edge.type] = edge
        return found

    found: dict[str, dict[str, Edge]] = {}
    for path in ("bulk", "upsert"):
        async with factory.context() as adapter:  # a fresh database for each path
            found[path] = await write(adapter, bulk=path == "bulk")
    labels = {"COMMUNICATED_WITH", "SELF_LOOP", "FAMILY_OF", "ASSOCIATE_OF"}
    assert set(found["bulk"]) == labels and set(found["upsert"]) == labels

    for path, edges in found.items():
        for label, edge in edges.items():
            components = edge.weight_components
            assert components is not None, (path, label)
            assert components.parameter_set == rules.parameter_set(edge.type), (path, label)
            assert edge.interval is not None
            recomputed = compute_weight(
                components,
                edge_type=edge.type,
                valid_to=edge.interval.valid_to,
                now=components.computed_at,
                rules=rules,
                self_loop=edge.source == edge.target,
            )
            assert edge.weight == pytest.approx(recomputed, abs=1e-9), (path, label)
        # The structural type weighs its strength; the unlisted one takes the default rule.
        assert edges["FAMILY_OF"].weight == 0.75, path
        unlisted = edges["ASSOCIATE_OF"]
        assert unlisted.weight_components is not None and unlisted.interval is not None
        assert unlisted.weight_components.parameter_set == f"{rules.version}/default", path
        as_communicated = compute_weight(
            unlisted.weight_components,
            edge_type="COMMUNICATED_WITH",
            valid_to=unlisted.interval.valid_to,
            now=unlisted.weight_components.computed_at,
            rules=rules,
            self_loop=False,
        )
        assert abs(unlisted.weight - as_communicated) > 1e-3, path
        loop = edges["SELF_LOOP"].weight_components
        assert loop is not None
        assert loop.corpus_source_degree == OTHER_OCCURRENCES + 2 * LOOP_OCCURRENCES, path

    # The same link stored by either path, in databases that hold the same things: exactly the same
    # components, and the same weight to the clock's difference between the two calls. (The
    # ordinary COMMUNICATED_WITH link is left out: an upsert weighs it before the self-loop is
    # written, a bulk load after.)
    for label in ("SELF_LOOP", "FAMILY_OF", "ASSOCIATE_OF"):
        from_bulk, from_upsert = found["bulk"][label], found["upsert"][label]
        assert from_bulk.weight_components is not None
        assert from_upsert.weight_components is not None
        assert without_clock(from_bulk.weight_components) == without_clock(
            from_upsert.weight_components
        ), label
        assert from_bulk.weight == pytest.approx(from_upsert.weight, abs=1e-6), label


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



# --- ADR-123: a link's weight comes from the link alone, on the bulk path -----------------------
#
# The bulk loader reads degrees and the type's total from the store, unfiltered, and weighs a link
# against them. The same two-store cases as `test_suite.py` (K is written by `bulk_load_edges`; L is
# in the store already, or in the same call), under the latest weights version and shown red under
# version 1. `now_utc` is pinned where `bulk.py` imports it and where `adapter.py` does.

_BULK_SHAPES = [(case, False) for case in ALL_CASES] + [(case, True) for case in HIDING_CASES]


@pytest.mark.parametrize(("case", "same_call"), _BULK_SHAPES)
async def test_a_bulk_loaded_links_weight_is_the_same_in_two_stores_that_differ_by_a_hidden_link(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, case: str, same_call: bool
) -> None:
    """ADR-123: the weight the bulk loader stores for a link the viewer can see is the same whether
    or not the store (or the same call) also holds a link the viewer cannot see: classified above
    them, restricted, to a node they cannot see, in another dataset, or raised afterwards. Catches a
    loader whose degrees or type total reach the weight."""
    without, with_link = await two_store_weights(
        factory, monkeypatch, case=case, path="bulk", same_call=same_call
    )
    assert with_link == without, (case, same_call, without, with_link)


@pytest.mark.parametrize(("case", "same_call"), _BULK_SHAPES)
async def test_the_bulk_two_store_case_is_red_under_weights_version_1(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch, case: str, same_call: bool
) -> None:
    """Rule 15 for the test above: the same stores with version 1's rules (gamma 0.3) give the
    bulk-loaded link two different weights, in every shape."""
    without, with_link = await two_store_weights(
        factory, monkeypatch, case=case, path="bulk", version=1, same_call=same_call
    )
    assert abs(with_link - without) > 1e-6, (case, same_call, without, with_link)


async def test_a_bulk_load_does_not_carry_another_datasets_occurrences_into_a_pair(
    factory: GraphAdapterFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-123 decision 4 recorded an open route on the bulk path as well as the upsert path: a case
    reading one dataset saw the occurrences another wrote to the same pair, in the link's count and
    its weight. ADR-102 Amendment 3 closes it. Two shapes, each giving a viewer of `fixture` alone
    a link of 2 occurrences, weighed as a link of 2:
    - one call holding an `enron` write of 5 and a `fixture` write of 2 to the pair, which the
      loader writes as two links;
    - a pair already stored from `enron` (5), and a `fixture` write of 2 bulk-loaded after it,
      which is not a collision (the stored link is another audience's) and is written as a link of
      its own."""
    from tests.conformance.graph_port.test_suite import IN_FIXTURE

    _pin_now(monkeypatch)

    async def stored_link(shape: str) -> Edge:
        async with factory.context() as adapter:
            loader = _loader(adapter)
            nodes = [
                _node(
                    "Endpoint",
                    classification="OFFICIAL",
                    datasets=["enron", "fixture"],
                    value_normalised=f"+44300000{n:04d}",
                )
                for n in range(2)
            ]
            (a, b), _ = await _write(adapter, nodes, [])

            def link(datasets: list[str], occurrences: int) -> EdgeWrite:
                return _link_k(a, b, occurrences=occurrences).model_copy(
                    update={"datasets": datasets}
                )

            if shape == "one_call":
                result = await loader.bulk_load_edges([link(["enron"], 5), link(["fixture"], 2)])
                assert len(result.written) == 2 and result.collisions == []
            elif shape == "stored_then_bulk":
                await _write(adapter, [], [link(["enron"], 5)])
                result = await loader.bulk_load_edges([link(["fixture"], 2)])
                assert len(result.written) == 1 and result.collisions == []
            else:
                await loader.bulk_load_edges([link(["fixture"], 2)])
            (seen,) = await adapter.edges_among([a, b], IN_FIXTURE)
            return seen

    two = await stored_link("two")
    for shape in ("one_call", "stored_then_bulk"):
        split = await stored_link(shape)
        assert split.datasets == ["fixture"], shape
        assert split.occurrences == 2, shape
        assert split.weight_components is not None and split.weight_components.occurrences == 2
        assert split.weight == pytest.approx(two.weight, abs=1e-9), shape


# --- ADR-102 Amendment 3: the bulk path merges only within one audience ---------------------------
#
# The same rule as `upsert_edges` (the cases are in `test_suite.py`): a pair already stored is handed
# back as a collision only when the stored link has the write's audience; one of another audience is
# not the write's to merge into, so the write is a link of its own. Within one call, repeated pairs
# collapse per audience.


async def _bulk_links(adapter: GraphPort, a: str, b: str, reader: Any) -> list[Edge]:
    return sorted(await adapter.edges_among([a, b], reader), key=lambda e: e.id)


def _marked(a: str, b: str, **kwargs: Any) -> EdgeWrite:
    return _edge("COMMUNICATED_WITH", a, b, **{"classification": "OFFICIAL", **kwargs})


async def test_bulk_a_stored_link_of_another_classification_is_not_a_collision(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, b = await _endpoints(adapter, 2)
        _, (official,) = await _write(adapter, [], [_marked(a, b)])
        secret = _marked(a, b, classification="SECRET")
        same = _marked(a, b)
        result = await _loader(adapter).bulk_load_edges([secret, same])
        assert result.written == [secret.id] and [c.id for c in result.collisions] == [same.id]
        from tests.conformance.graph_port.test_suite import OFFICIAL as official_reader

        assert [e.id for e in await _bulk_links(adapter, a, b, official_reader)] == [official]
        assert len(await _bulk_links(adapter, a, b, CLEARED)) == 2


async def test_bulk_one_call_splits_a_pair_by_audience_and_merges_within_one(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        a, b = await _endpoints(adapter, 2)
        writes = [
            _marked(a, b),
            _marked(a, b, classification="SECRET"),
            _marked(a, b),
            _marked(a, b, handling_code="R", owning_unit="unit-1", originator="unit-1"),
            _marked(a, b, handling_code="R", owning_unit="unit-2", originator="unit-2"),
            _marked(a, b, datasets=["enron"]),
            _marked(a, b, datasets=["fixture"]),
            _marked(a, b, handling_code="C", owning_unit="unit-1"),
            _marked(a, b, handling_code="C", owning_unit="unit-2"),
        ]
        result = await _loader(adapter).bulk_load_edges(writes)
        # OFFICIAL, SECRET, R/unit-1, R/unit-2, enron, fixture, C: seven links; C merged its units.
        assert len(result.written) == 7 and result.collisions == []
        assert len(set(result.written)) == 7, "each link has an id of its own"
        # A reader reads what their clearance and units allow, so no one reader reads all seven:
        # CLEARED holds no restricted code, and each unit's reader reads only its own restricted
        # link. Together they account for every one of the seven.
        from tests.conformance.graph_port.test_suite import UNIT_1, UNIT_2

        open_links = await _bulk_links(adapter, a, b, CLEARED)
        assert sorted(e.occurrences for e in open_links) == [1, 1, 1, 2, 2]
        restricted = {
            e.id: e.occurrences
            for reader in (UNIT_1, UNIT_2)
            for e in await _bulk_links(adapter, a, b, reader)
            if e.handling.handling_code == "R"
        }
        assert sorted(restricted.values()) == [1, 1]
        assert {e.id for e in open_links} | set(restricted) == set(result.written)


async def test_bulk_an_undirected_pair_stored_reversed_collides_only_within_its_audience(
    factory: GraphAdapterFactory,
) -> None:
    async with factory.context() as adapter:
        (a, b), _ = await _write(
            adapter, [_node("Person", classification="OFFICIAL"), _node("Person", classification="OFFICIAL")], []
        )
        _, (stored,) = await _write(adapter, [], [_edge("ASSOCIATE_OF", a, b, classification="OFFICIAL")])
        same = _edge("ASSOCIATE_OF", b, a, classification="OFFICIAL")
        secret = _edge("ASSOCIATE_OF", b, a, classification="SECRET")
        result = await _loader(adapter).bulk_load_edges([same, secret])
        assert [c.id for c in result.collisions] == [same.id] and result.written == [secret.id]
        assert stored not in result.written


async def test_bulk_a_fixed_id_in_two_audiences_is_two_links_under_two_ids(
    factory: GraphAdapterFactory,
) -> None:
    """Writers that fix a link's id send one id for every audience of a pair, and edge `id` is
    UNIQUE. In one call, and against a stored link of another audience, the loader gives the second
    a new id and reports the ids as stored; no row is refused."""
    async with factory.context() as adapter:
        a, b = await _endpoints(adapter, 2)
        fixed = _marked(a, b).model_copy(update={"id": f"{a}:fixed:{b}"})
        secret = fixed.model_copy(
            update={"handling": fixed.handling.model_copy(update={"classification": "SECRET"})}
        )
        result = await _loader(adapter).bulk_load_edges([fixed, secret])
        assert result.collisions == [] and len(set(result.written)) == 2
        assert fixed.id in result.written
        from tests.conformance.graph_port.test_suite import OFFICIAL as official_reader

        assert [e.id for e in await _bulk_links(adapter, a, b, official_reader)] == [fixed.id]

        # A third audience, against the two stored: one more link, one more id.
        restricted = fixed.model_copy(
            update={"handling": fixed.handling.model_copy(
                update={"handling_code": "R", "owning_unit": "unit-1", "originator": "unit-1"}
            )}
        )
        again = await _loader(adapter).bulk_load_edges([restricted])
        assert again.collisions == [] and len(again.written) == 1 and again.written[0] != fixed.id
        assert len(await _bulk_links(adapter, a, b, CLEARED)) == 2, "R is not CLEARED's to read"


async def test_a_bulk_load_of_writes_standing_for_several_holds_their_sum_as_the_revision(
    factory: GraphAdapterFactory,
) -> None:
    """ADR-127 Amendment 19: the revision counts the writes a link stands for, not the list items
    the loader received. Catches the aggregate counting items, so a pair sent as two writes
    standing for 3 and 4 (and a third for 1) is left at revision 3 instead of 8, and a single write
    standing for 5 at 1 instead of 5."""
    async with factory.context() as adapter:
        loader = _loader(adapter)
        a, b, c, d = await _endpoints(adapter, 4)
        writes = [
            _comm(a, b, row="r1").model_copy(update={"writes": 3}),
            _comm(a, b, row="r2").model_copy(update={"writes": 4}),
            _comm(a, b, row="r3"),
            _comm(c, d, row="r4").model_copy(update={"writes": 5}),
        ]
        await loader.bulk_load_edges(writes)
        (pair,) = await _edges_of(adapter, a)
        (single,) = await _edges_of(adapter, c)
        assert pair.audit.revision == 8
        assert single.audit.revision == 5
