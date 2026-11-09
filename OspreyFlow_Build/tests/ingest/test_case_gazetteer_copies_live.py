"""A case's copies of a gazetteer's places, against a live ArcadeDB (ADR-147 Amendment 2, the owner's
ruling 6 of 9 November 2026, option C).

The gazetteer is loaded as every build loads it (`scripts.build_local_basemap.load_gazetteer`, from
a synthetic extract: rule 9) into `gazetteer-osm-rutland`, with its points, and copied into a case's
own dataset (`case_gazetteers.copy_places`). A reader of that case alone (its principal reads
`case-a`, never the gazetteer's dataset) then:

- **finds the place by its name** in the map's place search, at the place's own point, and not a
  SECRET place above its clearance;
- **is sent no copy's identifier** on any node read (`get_node`, the store's search, expansion);
- **never matches a copy by an identifier** in the case's own searches: the exact search by its
  `osm_id` finds nothing, the type-ahead on the identifier's prefix (more places than a page share
  it) suggests nothing and says no `more` (decision 3b, keyed on the copy's provenance, since a copy
  is in no `gazetteer-*` dataset);
- **a re-copy writes no second copy**, and a place the gazetteer no longer holds has its copy
  reverted; **a removal keeps the copy a case's link rests on** (in the dataset or a case's layer)
  and reverts the rest; **a case's load writing onto a copy** keeps it a copy, withheld, and makes
  it the case's: a re-build does not write over it and a removal keeps it; **a region is copied in
  pages**, timed.

Each shown red with its fix removed (`P5_RED_RECORD.md`). The routes themselves, over the
Conduit's shared database, are `test_case_gazetteer_routes_live.py`. Live, so under `tests/ingest`
(outside `make test`), run under a test-stack lease; the throwaway database is dropped in teardown,
pass or fail (`arcadedb_adapter`), and the analytics store is in memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from scripts.build_local_basemap import load_gazetteer
from services.api.case_gazetteers import copy_id, copy_places, remove_copies
from services.api.map_places import gazetteer_dataset_id, search_places
from services.ingest.geometries import POINT_GEOMETRY_VERSION

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import SuggestOptions
from schemas.analytics import GeometryKind, GeometryRecord
from schemas.domain import (
    EdgeWrite,
    ExpandRequest,
    Interval,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.mapconfig import GAZETTEER_SOURCE_IDENTIFIERS, PlaceSearchRequest
from tests.scenarios.fixtures.osm_extract import build_synthetic_osm_pbf

GAZETTEER = gazetteer_dataset_id("rutland")
BUILDER = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[])
#: A reader of the case alone: its own dataset, never the gazetteer's.
CASE = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=["case-a"])
#: Every place this run plants shares this prefix in its `osm_id`, never in its name.
PREFIX = "osm-p5-7731"
SCHEME = load_uk_le_scheme()

Stores = tuple[GraphArcadeDBAdapter, AnalyticsDuckDBAdapter, Path]


@pytest.fixture
async def stores(tmp_path: Path) -> AsyncIterator[Stores]:
    con = duckdb.connect(":memory:")
    create_events_table(con)
    create_geometries_table(con)
    extract = tmp_path / "rutland.osm.pbf"
    build_synthetic_osm_pbf(extract)
    try:
        async with arcadedb_adapter(load_default_ontology(), SCHEME) as graph:
            yield graph, AnalyticsDuckDBAdapter(con, SCHEME), extract
    finally:
        con.close()


async def _load(stores: Stores) -> None:
    graph, analytics, extract = stores
    tx = await graph.begin_transaction()
    await load_gazetteer(
        extract, graph=graph, ontology=load_default_ontology(), tx=tx, principal=BUILDER,
        load_id="load-osm-gazetteer-rutland", dataset=GAZETTEER, analytics=analytics,
        unit="unit-1",
    )  # fmt: skip
    await graph.commit_transaction(tx)


def _place(node_id: str, name: str, *, classification: str = "OFFICIAL", **props: str) -> NodeWrite:
    """A gazetteer place as a load writes it, in the gazetteer's dataset."""
    return NodeWrite(
        id=node_id, type="Location", properties={"name": name, **props},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="osm", locator="1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling={"classification": classification, "handling_code": "P",  # type: ignore[arg-type]
                  "originator": "unit-1", "owning_unit": "unit-1"},
        created_by="loader", created_at=datetime(2026, 1, 1, tzinfo=UTC), datasets=[GAZETTEER],
    )  # fmt: skip


async def _plant(stores: Stores) -> None:
    """A place with identifiers and a point, a SECRET one, and twelve sharing its `osm_id` prefix:
    more than a type-ahead page."""
    graph, analytics, _ = stores
    writes = [
        _place("01JP5ASHWELL00000000000000", "Ashwell", osm_id=f"{PREFIX}", uprn="100077441",
               geometry_ref="g-ashwell"),
        _place("01JP5DEPOT0000000000000000", "Ashwell Depot", classification="SECRET",
               osm_id=f"{PREFIX}99", geometry_ref="g-depot"),
        *(_place(f"01JP5ALIKE{i:02d}00000000000000", f"Elsewhere {i}", osm_id=f"{PREFIX}{i:02d}")
          for i in range(12)),
    ]  # fmt: skip
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(writes, tx)
    await graph.commit_transaction(tx)
    await analytics.load_geometries(
        [
            GeometryRecord(
                geometry_ref=ref, version=POINT_GEOMETRY_VERSION, kind=GeometryKind.POINT,
                lon=-0.7, lat=52.7,
                handling={"classification": "OFFICIAL", "handling_code": "P",  # type: ignore[arg-type]
                          "originator": "unit-1", "owning_unit": "unit-1"},
            )
            for ref in ("g-ashwell", "g-depot")
        ]
    )  # fmt: skip


async def _copy(graph: GraphArcadeDBAdapter) -> list[str]:
    return await copy_places(
        graph, SCHEME, gazetteer=GAZETTEER, case_dataset="case-a", by="author-1"
    )


def _no_identifier(properties: dict[str, object]) -> bool:
    return not set(properties) & set(GAZETTEER_SOURCE_IDENTIFIERS)


async def test_a_case_finds_its_copy_of_a_place_by_name_at_its_point(stores: Stores) -> None:
    graph, analytics, _ = stores
    await _load(stores)
    await _plant(stores)
    nothing = await search_places(graph, analytics, PlaceSearchRequest(query="ashw"), CASE)
    assert nothing.places == [], "the case reads no gazetteer before it adds one"
    await _copy(graph)

    found = await search_places(graph, analytics, PlaceSearchRequest(query="ashw"), CASE)
    # The copy, not the place: the case reads only its own dataset. Not the SECRET depot (rule 3).
    assert [(p.id, p.name) for p in found.places] == [
        (copy_id("01JP5ASHWELL00000000000000", "case-a"), "Ashwell")
    ]
    assert found.more is False
    built = await search_places(graph, analytics, PlaceSearchRequest(query="cranf"), CASE)
    assert [p.name for p in built.places] == ["Cranford"]  # a built place, copied too


async def test_no_copy_s_identifier_is_sent_on_any_node_read(stores: Stores) -> None:
    graph, _analytics, _ = stores
    await _plant(stores)
    await _copy(graph)
    copy = copy_id("01JP5ASHWELL00000000000000", "case-a")
    read = await graph.get_node(copy, CASE)
    assert read is not None and read.properties["name"] == "Ashwell"
    assert _no_identifier(read.properties), read.properties
    assert read.datasets == ["case-a"] and read.provenance.gazetteer == GAZETTEER
    # A case's own link to it (a person present there), so the copy arrives by expansion too.
    person = _place("01JP5PERSON000000000000000", "x").model_copy(
        update={"type": "Person", "properties": {"family_name": "Quill"}, "datasets": ["case-a"]}
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([person], tx)
    await graph.upsert_edges([_present_at(person.id, copy)], tx)
    await graph.commit_transaction(tx)
    around = await graph.expand(ExpandRequest(node_ids=[person.id], depth=1), CASE)
    [arrived] = [n for n in around.nodes if n.id == copy]
    assert _no_identifier(arrived.properties), arrived.properties
    by_name = await graph.search_nodes("Ashwell", CASE)
    assert all(_no_identifier(n.properties) for n in by_name)
    # The Conduit's own work keeps them (a rebuild's lookups), as a read written back does.
    unlimited = CASE.model_copy(update={"datasets": None})
    whole = await graph.get_node(copy, unlimited)
    assert whole is not None and whole.properties["osm_id"] == PREFIX


def _present_at(source: str, target: str) -> EdgeWrite:
    return EdgeWrite(
        id=f"01JP5LINK{source[-4:]}0000000000000"[:26], type="PRESENT_AT", source=source,
        target=target, interval=Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC)),
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="case-load", locator="row 1", excerpt_hash="")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling={"classification": "OFFICIAL", "handling_code": "P",  # type: ignore[arg-type]
                  "originator": "unit-1", "owning_unit": "unit-1"},
        created_by="analyst-1", created_at=datetime(2026, 1, 1, tzinfo=UTC), datasets=["case-a"],
    )  # fmt: skip


async def test_the_case_s_own_searches_never_match_a_copy_by_an_identifier(stores: Stores) -> None:
    """Decision 3b for a copy: twelve copies share the planted `osm_id` prefix, more than a page."""
    graph, _analytics, _ = stores
    await _plant(stores)
    await _copy(graph)
    assert await graph.search_nodes(PREFIX, CASE) == []
    assert await graph.search_nodes("100077441", CASE) == []
    for options in (None, SuggestOptions(mode="contains", ignore_case=True)):
        hinted = await graph.suggest_nodes(PREFIX, CASE, limit=10, options=options)
        assert (hinted.nodes, hinted.more) == ([], False), options
    # Positive controls: by its name it is found, and the Conduit's own work finds it by its id.
    named = await graph.suggest_nodes("Ashwe", CASE, limit=10)
    assert [n.properties["name"] for n in named.nodes] == ["Ashwell"]
    unlimited = CASE.model_copy(update={"datasets": None})
    assert len(await graph.search_nodes(PREFIX, unlimited)) == 2  # the place and its copy


async def test_a_re_copy_writes_no_second_copy_and_reverts_a_place_gone(stores: Stores) -> None:
    graph, _analytics, _ = stores
    await _plant(stores)
    await _copy(graph)
    gone = "01JP5ALIKE0000000000000000"
    tx = await graph.begin_transaction()
    await graph.revert_elements([gone], [], tx)  # the gazetteer no longer holds it
    await graph.commit_transaction(tx)
    reverted = await _copy(graph)
    assert reverted == [copy_id(gone, "case-a")]
    named = await graph.suggest_nodes("Ashwe", CASE, limit=10)
    assert len(named.nodes) == 1


async def test_a_removal_keeps_a_copy_a_case_s_link_rests_on_in_the_dataset_or_a_layer(
    stores: Stores,
) -> None:
    """The orchestrator's review of P5, item 7: a copy a case's own link rests on is kept with its
    mark, so no case is left a link to nothing; the links read in the dataset and in a case's
    analyst layer (`link_datasets`). Every other copy of the gazetteer's alone is reverted."""
    graph, _analytics, _ = stores
    await _plant(stores)
    await _copy(graph)
    in_dataset = copy_id("01JP5ASHWELL00000000000000", "case-a")
    in_layer = copy_id("01JP5ALIKE0100000000000000", "case-a")
    person = _place("01JP5PERSON000000000000000", "x").model_copy(
        update={"type": "Person", "properties": {"family_name": "Quill"}, "datasets": ["case-a"]}
    )
    layer_link = _present_at(person.id, in_layer).model_copy(
        update={"id": "01JP5LAYERLINK000000000000", "datasets": ["layer-a"]}
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([person], tx)
    await graph.upsert_edges([_present_at(person.id, in_dataset), layer_link], tx)
    await graph.commit_transaction(tx)
    reverted, kept = await remove_copies(
        graph, SCHEME, gazetteer=GAZETTEER, case_dataset="case-a", link_datasets=["layer-a"],
        unit="unit-1",
    )  # fmt: skip
    assert sorted(kept) == sorted([in_dataset, in_layer])
    assert in_dataset not in reverted and in_layer not in reverted and reverted
    left = await graph.get_node(in_dataset, CASE)
    assert left is not None and left.provenance.gazetteer == GAZETTEER
    assert _no_identifier(left.properties)
    around = await graph.expand(ExpandRequest(node_ids=[person.id], depth=1), CASE)
    assert in_dataset in {n.id for n in around.nodes}  # no link to nothing


async def test_a_rebuild_after_a_case_s_load_keeps_what_the_case_wrote(stores: Stores) -> None:
    """Item 1: a copy the case has written to is the case's data now; a re-build does not write the
    gazetteer's values back over it, though the merge would keep the newest."""
    graph, _analytics, _ = stores
    await _plant(stores)
    await _copy(graph)
    copy = copy_id("01JP5ASHWELL00000000000000", "case-a")
    loaded = _place(copy, "Ashwell (the yard's spelling)", osm_id=PREFIX).model_copy(
        update={
            "datasets": ["case-a"],
            "provenance": Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[SourceRef(document_id="case-load", locator="row 7", excerpt_hash="")],
                first_seen=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        }
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([loaded], tx)
    await graph.commit_transaction(tx)
    await _copy(graph)  # the re-build's refresh
    read = await graph.get_node(copy, CASE)
    assert read is not None and read.properties["name"] == "Ashwell (the yard's spelling)"
    assert read.provenance.gazetteer == GAZETTEER


async def test_a_region_is_copied_in_bounded_pages_and_timed(stores: Stores) -> None:
    """Item 9: 2,000 planted places (four pages of 500, each its own transaction), timed for the
    report. Synthetic, so the figure is a rate per place on this stack, not a real region's."""
    import time

    graph, _analytics, _ = stores
    places = [
        _place(f"01JP5BULK{i:05d}000000000000"[:26], f"Bulkton {i}", osm_id=f"bulk-{i}")
        for i in range(2000)
    ]
    for start in range(0, len(places), 500):
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(places[start : start + 500], tx)
        await graph.commit_transaction(tx)
    began = time.perf_counter()
    await _copy(graph)
    took = time.perf_counter() - began
    print(f"\nP5 TIMING: copied 2000 places in {took:.1f} s ({took / 2:.2f} s per 1,000)")
    unlimited = CASE.model_copy(update={"datasets": None})
    copies = [copy_id(p.id, "case-a") for p in places[:5]]
    for made in copies:
        assert await graph.get_node(made, unlimited) is not None


async def test_a_case_s_load_writing_onto_a_copy_keeps_it_a_copy_and_the_case_s(
    stores: Stores,
) -> None:
    """ADR-147 Amendment 2: a case's own load may match a copy by its `osm_id` and write onto it,
    through the store's real merge (`upsert_nodes`). Its provenance keeps the gazetteer, so its
    identifiers stay withheld and unmatched; and it is now another writer's too, so a removal keeps
    it (rule 6)."""
    graph, _analytics, _ = stores
    await _plant(stores)
    await _copy(graph)
    copy = copy_id("01JP5ASHWELL00000000000000", "case-a")
    loaded = _place(copy, "Ashwell", osm_id=PREFIX, geometry_ref="g-ashwell").model_copy(
        update={
            "datasets": ["case-a"],
            "provenance": Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[SourceRef(document_id="case-load", locator="row 7", excerpt_hash="")],
                first_seen=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        }
    )
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([loaded], tx)
    await graph.commit_transaction(tx)
    read = await graph.get_node(copy, CASE)
    assert read is not None and read.provenance.gazetteer == GAZETTEER
    assert _no_identifier(read.properties), read.properties
    assert await graph.search_nodes(PREFIX, CASE) == []
    _reverted, kept = await remove_copies(
        graph, SCHEME, gazetteer=GAZETTEER, case_dataset="case-a"
    )
    assert copy in kept
