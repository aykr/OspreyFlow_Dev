"""A case's gazetteers (ADR-147 Amendment 2, the owner's ruling 6): `GET`, `PUT` and `DELETE
/v1/investigations/{id}/map/gazetteers[/{dataset_id}]`, through the real app with the graph stood in.

What the stand-in can prove, and only that: which gazetteers are offered (the Author's unit's), which
additions are refused and in what words (another unit's, not a gazetteer, a case reading a composite
or nothing), what a copy is written as (the case's own dataset, the place's handling and properties,
its provenance naming the gazetteer, the same id each time), and which copies a removal reverts (the
gazetteer's alone: never one another writer wrote or a link rests on, rule 6). That the store reads
and writes them under the access step, and that a copy's identifiers are withheld and never matched,
is proven live (`tests/ingest/test_case_gazetteer_copies_live.py`). The case levels are
`test_investigation_levels.py`'s table and the rights `test_route_rights.py`'s.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_case_gazetteers,
    get_datasets,
    get_graph,
    get_handling_scheme,
    get_investigations,
    get_principal,
    get_working_set,
)
from services.api.case_gazetteers import COPY_SOURCE_PREFIX, InMemoryCaseGazetteerStore, copy_id
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore

from ontology.handling import load_uk_le_scheme
from ports.graph import ListNodesPage
from schemas.domain import (
    AuditStub,
    Edge,
    ExpandRequest,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)
from tests.services.api.any_case import AnyCase
from tests.services.api.test_search_route import _FakeAudit

AUTHOR = Principal(
    id="author-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], datasets=["case-a"]
)
GAZ = "gazetteer-osm-rutland"
HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-7",
            "owning_unit": "unit-7"}  # fmt: skip
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _node(node_id: str, dataset: str, *, gazetteer: str | None = None, **props: Any) -> Node:
    sources = [SourceRef(document_id="/srv/rutland.osm.pbf", locator="row 1", excerpt_hash="")]
    if gazetteer:
        sources = [SourceRef(document_id=COPY_SOURCE_PREFIX + gazetteer, locator="place x",
                             excerpt_hash="")]  # fmt: skip
    return Node(
        id=node_id, type="Location", properties=props, datasets=[dataset],
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=sources, first_seen=NOW,
                              gazetteer=gazetteer),
        handling=HANDLING,  # type: ignore[arg-type]
        audit=AuditStub(created_at=NOW, created_by="loader"),
    )  # fmt: skip


PLACE = _node("01JCRANFORD0000000000000000", GAZ, name="Cranford", osm_id="node/31337",
              geometry_ref="g1")  # fmt: skip


class _Graph:
    """The calls the copier makes, as the store answers them: `list_nodes` gives the nodes of the
    reader's datasets only (the access step), a page at a time, `next_cursor` `None` at the end."""

    def __init__(self, nodes: list[Node]) -> None:
        self.nodes = {n.id: n for n in nodes}
        self.links: list[Edge] = []
        self.written: list[NodeWrite] = []
        self.reverted: list[str] = []
        self.readers: list[Principal] = []

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, _tx: str) -> None:
        pass

    async def rollback_transaction(self, _tx: str) -> None:
        pass

    async def list_nodes(
        self, entity_type: str, principal: Principal, *, cursor: str | None = None, limit: int = 500
    ) -> ListNodesPage:
        self.readers.append(principal)
        held = sorted(
            (n for n in self.nodes.values()
             if n.type == entity_type and set(n.datasets) & set(principal.datasets or [])
             and n.id not in self.reverted and (cursor is None or n.id > cursor)),
            key=lambda n: n.id,
        )  # fmt: skip
        page = held[:limit]
        return ListNodesPage(nodes=page, next_cursor=page[-1].id if len(held) > limit else None)

    async def upsert_nodes(self, writes: Sequence[NodeWrite], _tx: str) -> list[str]:
        for w in writes:
            self.written.append(w)
            self.nodes[w.id] = Node(
                id=w.id, type=w.type, properties=w.properties, provenance=w.provenance,
                handling=w.handling, datasets=w.datasets,
                audit=AuditStub(created_at=w.created_at, created_by=w.created_by),
            )  # fmt: skip
            if w.id in self.reverted:
                self.reverted.remove(w.id)
        return [w.id for w in writes]

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        edges = [e for e in self.links if {e.source, e.target} & set(req.node_ids)]
        return Subgraph(nodes=[], edges=edges)

    async def revert_elements(self, nodes: Sequence[str], edges: Sequence[str], _tx: str) -> None:
        self.reverted.extend(nodes)

    async def get_nodes(self, ids: Sequence[str], principal: Principal) -> list[Node]:
        return [self.nodes[i] for i in ids if i in self.nodes and i not in self.reverted]


class _WorkingSet:
    publisher = None

    def __init__(self) -> None:
        self.removed: list[str] = []

    async def remove_reverted(self, nodes: Sequence[str], edges: Sequence[str]) -> list[Any]:
        self.removed.extend(nodes)
        return []


World = tuple[_Graph, InMemoryDatasetStore, InMemoryCaseGazetteerStore, _FakeAudit, _WorkingSet]


def _dataset(dataset_id: str, unit: str, kind: str = "source") -> Dataset:
    return Dataset(id=dataset_id, name=dataset_id.title(), owning_unit=unit, created_at=NOW,
                   created_by="someone", kind=kind)  # type: ignore[arg-type]  # fmt: skip


@pytest.fixture
def world() -> Iterator[World]:
    graph = _Graph([PLACE])
    datasets = InMemoryDatasetStore()
    for held in (_dataset(GAZ, "unit-1"), _dataset("gazetteer-osm-elsewhere", "unit-2"),
                 _dataset("case-a", "unit-1"), _dataset("plain", "unit-1")):  # fmt: skip
        datasets.datasets[held.id] = held
    datasets.cases["inv-1"] = ["case-a"]
    store = InMemoryCaseGazetteerStore()
    audit = _FakeAudit()
    working_set = _WorkingSet()
    app.dependency_overrides[get_principal] = lambda: AUTHOR
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_datasets] = lambda: datasets
    app.dependency_overrides[get_case_gazetteers] = lambda: store
    app.dependency_overrides[get_handling_scheme] = load_uk_le_scheme
    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_working_set] = lambda: working_set
    yield graph, datasets, store, audit, working_set
    app.dependency_overrides.clear()


def _client() -> TestClient:
    return TestClient(app)


def test_the_unit_s_gazetteers_are_offered_by_name_and_none_is_added_yet(world: World) -> None:
    response = _client().get("/v1/investigations/inv-1/map/gazetteers")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "gazetteers": [{"dataset_id": GAZ, "name": "Gazetteer-Osm-Rutland", "added": False}],
        "copies_kept": False,
    }


@pytest.mark.parametrize("dataset_id", ["gazetteer-osm-elsewhere", "plain", "gazetteer-osm-none"])
def test_only_a_gazetteer_of_the_author_s_unit_may_be_added(world: World, dataset_id: str) -> None:
    graph, *_ = world
    response = _client().put(f"/v1/investigations/inv-1/map/gazetteers/{dataset_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "There is no gazetteer of that name for this case's unit."
    assert graph.written == []


@pytest.mark.parametrize("reads", ["composite", "nothing"])
def test_a_case_without_one_dataset_of_its_own_is_refused_in_words(
    world: World, reads: str
) -> None:
    graph, datasets, store, *_ = world
    if reads == "composite":
        datasets.datasets["comp"] = _dataset("comp", "unit-1", kind=COMPOSITE)
        datasets.cases["inv-1"] = ["comp"]
    else:
        datasets.cases["inv-1"] = []
    response = _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert response.status_code == 409
    what = "a composite" if reads == "composite" else "no dataset"
    assert response.json()["detail"].startswith(f"This case reads {what}, so a gazetteer's")
    assert (graph.written, store.added) == ([], {})


def test_adding_copies_each_place_into_the_case_s_own_dataset(world: World) -> None:
    graph, _datasets, store, audit, _ws = world
    response = _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert response.status_code == 200, response.text
    assert response.json()["gazetteers"][0]["added"] is True
    [copy] = graph.written
    assert copy.id == copy_id(PLACE.id, "case-a") != PLACE.id
    assert copy.datasets == ["case-a"]
    assert copy.properties == PLACE.properties  # stored whole; withheld on every read
    assert copy.handling == PLACE.handling
    assert copy.provenance.gazetteer == GAZ
    # Its one source is the gazetteer: never the extract's server path or row.
    assert [(s.document_id, s.locator) for s in copy.provenance.sources] == [
        (f"gazetteer:{GAZ}", f"place {PLACE.id}")
    ]
    # The places are read from the gazetteer's dataset alone.
    assert graph.readers[0].datasets == [GAZ]
    assert [a.case_dataset for a in store.added.values()] == ["case-a"]
    assert audit.records[-1]["action"] == "add_case_gazetteer"
    assert audit.records[-1]["resolved_query"] == {"gazetteer": GAZ}
    # Again: the same copy, written again, not a second.
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert {w.id for w in graph.written} == {copy.id}


def test_copying_again_reverts_the_copy_of_a_place_the_gazetteer_no_longer_holds(
    world: World,
) -> None:
    graph, _datasets, _store, _audit, working_set = world
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    del graph.nodes[PLACE.id]  # a re-build without it
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert graph.reverted == [copy_id(PLACE.id, "case-a")]
    assert working_set.removed == graph.reverted


def test_removing_reverts_the_gazetteer_s_own_copies_and_never_another_writer_s(
    world: World,
) -> None:
    """Rule 6: a copy a case's own load also wrote (a source not the gazetteer's), or an analyst
    confirmed, is the case's data now and is kept; `copies_kept` says so. A link resting on a copy
    is no reason (rule 3: it may be one the Author cannot see): the copy goes, and the link with it
    out of every read, until the gazetteer is added again."""
    graph, _datasets, store, audit, working_set = world
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    alone = copy_id(PLACE.id, "case-a")
    written = _node("01JWRITTEN0000000000000000", "case-a", gazetteer=GAZ, name="Uppingham")
    written.provenance.sources.append(
        SourceRef(document_id="case-load", locator="row 3", excerpt_hash="")
    )
    confirmed = _node("01JCONFIRMED00000000000000", "case-a", gazetteer=GAZ, name="Oakham")
    confirmed.provenance.confirmed_by = "analyst-2"
    confirmed.provenance.last_confirmed = NOW
    linked = _node("01JLINKED00000000000000000", "case-a", gazetteer=GAZ, name="Exton")
    graph.nodes.update({n.id: n for n in (written, confirmed, linked)})
    graph.links.append(Edge.model_construct(id="e1", source="someone", target=linked.id))
    response = _client().delete(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert response.status_code == 200, response.text
    assert sorted(graph.reverted) == sorted([alone, linked.id])
    assert sorted(working_set.removed) == sorted(graph.reverted)
    assert response.json() == {
        "gazetteers": [{"dataset_id": GAZ, "name": "Gazetteer-Osm-Rutland", "added": False}],
        "copies_kept": True,
    }
    assert store.added == {}
    assert audit.records[-1]["action"] == "remove_case_gazetteer"
    # Added again: the same copies written again, so a link that rested on one rests on it again.
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert alone not in graph.reverted


def test_the_addition_is_the_dataset_s_so_every_case_reading_it_sees_it(world: World) -> None:
    """Copies are in the dataset, which several cases may read (a case opened from an alert reads
    its case's): each sees the gazetteer added, and none's removal leaves another's record saying
    copies are there that are not."""
    graph, datasets, store, *_ = world
    datasets.cases["inv-2"] = ["case-a"]
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    seen = _client().get("/v1/investigations/inv-2/map/gazetteers").json()
    assert seen["gazetteers"][0]["added"] is True
    assert [a.added_in for a in store.added.values()] == ["inv-1"]
    _client().delete(f"/v1/investigations/inv-2/map/gazetteers/{GAZ}")
    first = _client().get("/v1/investigations/inv-1/map/gazetteers").json()
    assert first["gazetteers"][0]["added"] is False
    assert copy_id(PLACE.id, "case-a") in graph.reverted


def test_a_failed_copy_again_keeps_the_earlier_addition(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _graph, _datasets, store, *_ = world
    _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")

    async def fails(*_args: Any, **_kwargs: Any) -> list[str]:
        raise RuntimeError("the store went away")

    monkeypatch.setattr("services.api.case_gazetteers.copy_places", fails)
    with pytest.raises(RuntimeError):
        _client().put(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert list(store.added) == [("case-a", GAZ)]


async def test_a_rebuild_refreshes_each_dataset_and_drops_one_no_longer_there(
    world: World,
) -> None:
    from services.api.case_gazetteers import AddedGazetteer, refresh_cases

    graph, datasets, store, *_ = world
    for held in ("case-a", "deleted-ds"):
        await store.add(AddedGazetteer(case_dataset=held, gazetteer=GAZ, added_in="inv-1",
                                       added_by="author-1", added_at=NOW))  # fmt: skip
    await refresh_cases(graph, load_uk_le_scheme(), store, datasets, GAZ)
    assert {w.datasets[0] for w in graph.written} == {"case-a"}
    assert list(store.added) == [("case-a", GAZ)]


def test_removing_a_gazetteer_the_case_never_added_is_refused(world: World) -> None:
    graph, *_ = world
    response = _client().delete(f"/v1/investigations/inv-1/map/gazetteers/{GAZ}")
    assert response.status_code == 404
    assert graph.reverted == []
