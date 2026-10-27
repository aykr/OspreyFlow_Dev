"""ADR-130 Amendment 2, on real ArcadeDB: a node or link in two datasets, read by a principal whose
case reads one of them, comes back with its sources withheld, by every read path that returns an
element; read by a principal whose case reads both, it names its sources. The element map's own
rule is held hermetically by `test_element_map_withholds_sources.py`; this is the proof that every
adapter read path passes the reader to it (rule 4, rule 12: a path that forgets would pass that
file and fail here).

Covers every adapter read that takes a principal and returns a node or a link: `get_node`,
`get_nodes`, `get_edges`, `find_node`, `search_nodes`, `suggest_locations`, `suggest_nodes`,
`list_nodes`, `expand`, `edges_among`, `paths`, `paths_at_length`, `match`, `most_connected`,
`busiest_links`, `recently_confirmed` and `shared_contacts`.

Needs a live ArcadeDB (`make conformance` runs the directory): run alone with
`cd OspreyFlow_Core && .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini \
../OspreyFlow_Build/tests/adapters/graph_arcadedb/test_sources_withheld_live.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    ExpandRequest,
    Handling,
    NodeWrite,
    PathRequest,
    PatternNode,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

ONTOLOGY = load_default_ontology()
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
TWO = ["Z1001ZZ", "Z1002ZZ"]
SOURCE = SourceRef(document_id="files/calls.csv", locator="row 3", excerpt_hash="d" * 64)
PROVENANCE = Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN)
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
NINO = "AB123456C"


def _reader(datasets: list[str] | None) -> Principal:
    return Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=datasets)


def _person(nino: str | None, datasets: list[str]) -> NodeWrite:
    return NodeWrite(
        id=new_node_id(),
        type="Person",
        properties={"family_name": "Quillfeather", **({"nino": nino} if nino else {})},
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="analyst-1",
        created_at=WHEN,
        datasets=datasets,
    )


async def _seed(graph):  # type: ignore[no-untyped-def]
    a, b = _person(NINO, TWO), _person(None, TWO)
    link = EdgeWrite(
        id=new_edge_id(),
        type="ASSOCIATE_OF",
        source=a.id,
        target=b.id,
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="analyst-1",
        created_at=WHEN,
        datasets=TWO,
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([a, b], tx)
    await graph.upsert_edges([link], tx)
    await graph.commit_transaction(tx)
    return a, b, link


async def test_every_read_path_withholds_sources_of_an_element_in_a_dataset_the_case_lacks() -> (
    None
):
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, b, link = await _seed(graph)
        one = _reader([TWO[0]])

        got = await graph.get_node(a.id, one)
        assert got is not None
        assert got.provenance.sources == [] and got.provenance.sources_withheld

        (found,) = await graph.get_nodes([a.id], one)
        assert found.provenance.sources_withheld and found.provenance.sources == []

        (hit,) = await graph.search_nodes(NINO, one)
        assert hit.id == a.id
        assert hit.provenance.sources_withheld and hit.provenance.sources == []

        sub = await graph.expand(ExpandRequest(node_ids=[a.id]), one)
        assert {n.id for n in sub.nodes} == {a.id, b.id}
        assert all(n.provenance.sources_withheld and not n.provenance.sources for n in sub.nodes)
        assert [e.id for e in sub.edges] == [link.id]
        assert sub.edges[0].provenance.sources_withheld and not sub.edges[0].provenance.sources

        (edge,) = await graph.get_edges([link.id], one)
        assert edge.provenance.sources_withheld and edge.provenance.sources == []

        (among,) = await graph.edges_among([a.id, b.id], one)
        assert among.provenance.sources_withheld and among.provenance.sources == []

        page = await graph.list_nodes("Person", one)
        assert page.nodes and all(n.provenance.sources_withheld for n in page.nodes)


async def test_a_case_reading_both_datasets_is_named_the_sources() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, b, link = await _seed(graph)
        both = _reader(TWO)

        got = await graph.get_node(a.id, both)
        assert got is not None
        assert got.provenance.sources == [SOURCE] and not got.provenance.sources_withheld

        (hit,) = await graph.search_nodes(NINO, both)
        assert hit.provenance.sources == [SOURCE]

        sub = await graph.expand(ExpandRequest(node_ids=[a.id]), both)
        assert all(n.provenance.sources == [SOURCE] for n in sub.nodes)
        assert sub.edges[0].provenance.sources == [SOURCE]


async def test_withholding_changes_what_is_sent_never_what_is_stored() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, _, _ = await _seed(graph)
        await graph.get_node(a.id, _reader([TWO[0]]))
        again = await graph.get_node(a.id, _reader(TWO))
        assert again is not None and again.provenance.sources == [SOURCE]
        unlimited = await graph.get_node(a.id, _reader(None))
        assert unlimited is not None and unlimited.provenance.sources == [SOURCE]


def _withheld(element) -> bool:  # type: ignore[no-untyped-def]
    return element.provenance.sources_withheld is True and element.provenance.sources == []


def _named(element) -> bool:  # type: ignore[no-untyped-def]
    return element.provenance.sources == [SOURCE] and not element.provenance.sources_withheld


async def _seed_wider(graph):  # type: ignore[no-untyped-def]
    """Three people and a place, all in both datasets: `a` and `c` each linked to `b`, `b` confirmed by
    an analyst, so that every remaining read path has something to return."""
    a, c = _person(NINO, TWO), _person(None, TWO)
    confirmed = Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SOURCE],
        first_seen=WHEN,
        last_confirmed=WHEN,
        confirmed_by="analyst-1",
    )
    b = _person(None, TWO).model_copy(update={"provenance": confirmed})
    place = NodeWrite(
        id=new_node_id(),
        type="Location",
        properties={"name": "Quillfeather Wharf"},
        provenance=PROVENANCE,
        handling=HANDLING,
        created_by="analyst-1",
        created_at=WHEN,
        datasets=TWO,
    )

    def link(source: NodeWrite, target: NodeWrite) -> EdgeWrite:
        return EdgeWrite(
            id=new_edge_id(),
            type="ASSOCIATE_OF",
            source=source.id,
            target=target.id,
            provenance=PROVENANCE,
            handling=HANDLING,
            created_by="analyst-1",
            created_at=WHEN,
            datasets=TWO,
        )

    ab, bc = link(a, b), link(c, b)  # both link into `b`, so `c` is `a`'s shared contact
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([a, b, c, place], tx)
    await graph.upsert_edges([ab, bc], tx)
    await graph.commit_transaction(tx)
    return a, b, c, ab, bc


async def test_the_remaining_read_paths_withhold_and_name_by_the_readers_scope() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        a, b, c, ab, bc = await _seed_wider(graph)
        for reader, expect in ((_reader([TWO[0]]), _withheld), (_reader(TWO), _named)):
            found = await graph.find_node("Person", "nino", NINO, reader)
            assert found is not None and expect(found)

            places = await graph.suggest_locations("Quill", reader)
            assert places and all(expect(n) for n in places)

            suggested = await graph.suggest_nodes("Quill", reader)
            assert suggested.nodes and all(expect(n) for n in suggested.nodes)

            paths = await graph.paths(PathRequest(source=a.id, target=c.id), reader)
            assert paths
            assert all(expect(n) for p in paths for n in p.nodes)
            assert all(expect(e) for p in paths for e in p.edges)

            routes = await graph.paths_at_length(a.id, c.id, 2, 5, reader)
            assert routes.paths
            assert all(expect(n) for p in routes.paths for n in p.nodes)
            assert all(expect(e) for p in routes.paths for e in p.edges)

            matched = await graph.match(
                PatternQuery(nodes=[PatternNode(var="p", entity_type="Person")], edges=[]), reader
            )
            assert matched.nodes and all(expect(n) for n in matched.nodes)

            ranked = await graph.most_connected(reader)
            assert ranked.nodes and all(expect(r.node) for r in ranked.nodes)

            busy = await graph.busiest_links(reader)
            assert busy.links
            assert all(expect(r.edge) and expect(r.source) and expect(r.target) for r in busy.links)

            confirmed = await graph.recently_confirmed(reader)
            assert [n.node.id for n in confirmed.nodes] == [b.id]
            assert expect(confirmed.nodes[0].node)

            shared = await graph.shared_contacts(
                a.id, reader, edge_type="ASSOCIATE_OF", min_shared=1
            )
            assert shared.contacts and all(expect(s.node) for s in shared.contacts)
