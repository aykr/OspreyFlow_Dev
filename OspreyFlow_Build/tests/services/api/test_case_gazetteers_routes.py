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
    Handling,
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

#: One of whose cases loads into `case-a` (so the dataset route's gate scopes them to it), holding
#: `run_pipelines` (the legacy `loader` role carries it alone).
AUTHOR = Principal(
    id="author-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst", "loader"],
    datasets=["case-a"],
)  # fmt: skip
_RANK = {"OFFICIAL": 0, "SECRET": 1, "TOP SECRET": 2}


def _reads(principal: Principal, datasets: list[str], classification: str) -> bool:
    """The store's access step, as far as these tests need it: the reader's datasets and clearance.
    A stand-in that read past either would accept what the real one refuses (rule 15)."""
    return bool(set(datasets) & set(principal.datasets or [])) and (
        _RANK[classification] <= _RANK[principal.clearance]
    )
GAZ = "gazetteer-osm-rutland"
HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
            "owning_unit": "unit-1"}  # fmt: skip
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _node(
    node_id: str, dataset: str, *, gazetteer: str | None = None, classification: str = "OFFICIAL",
    **props: Any,
) -> Node:
    sources = [SourceRef(document_id="/srv/rutland.osm.pbf", locator="row 1", excerpt_hash="")]
    if gazetteer:
        sources = [SourceRef(document_id=COPY_SOURCE_PREFIX + gazetteer, locator="place",
                             excerpt_hash="")]  # fmt: skip
    return Node(
        id=node_id, type="Location", properties=props, datasets=[dataset],
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=sources, first_seen=NOW,
                              gazetteer=gazetteer),
        handling={**HANDLING, "classification": classification},  # type: ignore[arg-type]
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
        self.expanded_as: list[Principal] = []

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
             if n.type == entity_type and _reads(principal, n.datasets, n.handling.classification)
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
        edges = [
            e for e in self.links
            if {e.source, e.target} & set(req.node_ids)
            and _reads(principal, e.datasets, e.handling.classification)
        ]  # fmt: skip
        self.expanded_as.append(principal)
        return Subgraph(nodes=[], edges=edges)

    async def revert_elements(self, nodes: Sequence[str], edges: Sequence[str], _tx: str) -> None:
        self.reverted.extend(nodes)

    async def get_nodes(self, ids: Sequence[str], principal: Principal) -> list[Node]:
        return [
            self.nodes[i] for i in ids
            if i in self.nodes and i not in self.reverted
            and _reads(principal, self.nodes[i].datasets, self.nodes[i].handling.classification)
        ]  # fmt: skip


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
    datasets.datasets["layer-inv-1"] = _dataset("layer-inv-1", "unit-1", kind="analyst_layer").model_copy(
        update={"layer_of": "inv-1"}
    )
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


def _put(gazetteer: str = GAZ, dataset: str = "case-a") -> Any:
    return TestClient(app).put(f"/v1/datasets/{dataset}/gazetteers/{gazetteer}")


def _delete(gazetteer: str = GAZ, dataset: str = "case-a") -> Any:
    return TestClient(app).delete(f"/v1/datasets/{dataset}/gazetteers/{gazetteer}")


def _listing(case: str = "inv-1") -> dict[str, Any]:
    return TestClient(app).get(f"/v1/investigations/{case}/map/gazetteers").json()  # type: ignore[no-any-return]


def test_the_dataset_unit_s_gazetteers_are_offered_by_name_and_none_is_added_yet(
    world: World,
) -> None:
    assert _listing() == {
        "gazetteers": [{"dataset_id": GAZ, "name": "Gazetteer-Osm-Rutland", "added": False}],
        "copies_kept": 0, "said": None,
    }  # fmt: skip


@pytest.mark.parametrize("gazetteer", ["plain", "gazetteer-osm-none"])
def test_only_a_gazetteer_may_be_added(world: World, gazetteer: str) -> None:
    graph, *_ = world
    response = _put(gazetteer)
    assert response.status_code == 404
    assert response.json()["detail"] == "There is no gazetteer of that name."
    assert graph.written == []


def test_another_unit_s_gazetteer_is_refused_in_words(world: World) -> None:
    """The orchestrator's review of P5, item 3: the gazetteer's unit is the dataset's."""
    graph, *_ = world
    response = _put("gazetteer-osm-elsewhere")
    assert response.status_code == 409
    assert response.json()["detail"].startswith("That gazetteer was built for another unit")
    assert graph.written == []


def test_a_dataset_the_asker_loads_into_is_the_only_one_they_may_change(world: World) -> None:
    """Item 6: a dataset-level action, behind the dataset route's own gate: a dataset none of the
    asker's cases loads into is answered as one that does not exist."""
    graph, *_ = world
    assert _put(dataset="plain").status_code == 404
    assert graph.written == []


def test_without_run_pipelines_nothing_is_added(world: World) -> None:
    graph, *_ = world
    app.dependency_overrides[get_principal] = lambda: AUTHOR.model_copy(
        update={"roles": ["analyst"]}
    )
    assert _put().status_code == 403
    assert _delete().status_code == 403
    assert graph.written == []


def test_a_composite_takes_no_gazetteer(world: World) -> None:
    graph, datasets, store, *_ = world
    datasets.datasets["comp"] = _dataset("comp", "unit-1", kind=COMPOSITE)
    app.dependency_overrides[get_principal] = lambda: AUTHOR.model_copy(update={"datasets": ["comp"]})
    assert _put(dataset="comp").status_code in (404, 409)
    assert (graph.written, store.added) == ([], {})


def test_adding_copies_each_place_into_the_dataset(world: World) -> None:
    graph, _datasets, store, audit, _ws = world
    response = _put()
    assert response.status_code == 200, response.text
    assert response.json()["gazetteers"][0]["added"] is True
    [copy] = graph.written
    assert copy.id == copy_id(PLACE.id, "case-a") != PLACE.id
    assert copy.datasets == ["case-a"]
    assert copy.properties == PLACE.properties  # stored whole; withheld on every read
    assert copy.handling == PLACE.handling
    assert copy.provenance.gazetteer == GAZ
    # Its one source is the gazetteer: never the place's node id, the extract's path or its row
    # (item 10, rule 7).
    assert [(s.document_id, s.locator) for s in copy.provenance.sources] == [
        (f"gazetteer:{GAZ}", "place")
    ]
    assert PLACE.id not in copy.model_dump_json()
    # The places are read from the gazetteer's dataset alone.
    assert [GAZ] in [r.datasets for r in graph.readers]
    assert list(store.added) == [("case-a", GAZ)]
    assert audit.records[-1]["action"] == "add_dataset_gazetteer"
    _put()
    assert {w.id for w in graph.written} == {copy.id}


def test_copying_again_reverts_the_copy_of_a_place_the_gazetteer_no_longer_holds(
    world: World,
) -> None:
    graph, _datasets, _store, _audit, working_set = world
    _put()
    del graph.nodes[PLACE.id]  # a re-build without it
    _put()
    assert graph.reverted == [copy_id(PLACE.id, "case-a")]
    assert working_set.removed == graph.reverted


def _case_s_copies(graph: _Graph) -> dict[str, Node]:
    """Copies a case has made its own: one its load wrote to, one an analyst confirmed, one its
    link rests on, and one of those above the Author's clearance."""
    written = _node("01JWRITTEN0000000000000000", "case-a", gazetteer=GAZ, name="Uppingham")
    written.provenance.sources.append(
        SourceRef(document_id="case-load", locator="row 3", excerpt_hash="")
    )
    confirmed = _node("01JCONFIRMED00000000000000", "case-a", gazetteer=GAZ, name="Oakham")
    confirmed.provenance.confirmed_by = "analyst-2"
    confirmed.provenance.last_confirmed = NOW
    linked = _node("01JLINKED00000000000000000", "case-a", gazetteer=GAZ, name="Exton")
    secret = _node("01JSECRET00000000000000000", "case-a", gazetteer=GAZ, name="Depot",
                   classification="SECRET")  # fmt: skip
    secret.provenance.sources.append(
        SourceRef(document_id="case-load", locator="row 9", excerpt_hash="")
    )
    made = {str(n.properties["name"]): n for n in (written, confirmed, linked, secret)}
    graph.nodes.update({n.id: n for n in made.values()})
    # The case's link to Exton is in its analyst layer, not the dataset (ADR-143 Amendment 1).
    graph.links.append(
        Edge.model_construct(id="e1", source="someone", target=linked.id, datasets=["layer-inv-1"],
                             handling=Handling(**HANDLING))  # fmt: skip
    )
    return made


def test_removing_reverts_the_gazetteer_s_own_copies_and_keeps_the_case_s(world: World) -> None:
    """Rule 6 and item 7: a copy a case's own load wrote, an analyst confirmed or a case's link
    rests on (in its analyst layer) is kept with its mark, so no link rests on nothing. Item 2:
    `copies_kept` counts only the kept copies the Author may read (rule 3)."""
    graph, _datasets, store, audit, working_set = world
    _put()
    kept = _case_s_copies(graph)
    response = _delete()
    assert response.status_code == 200, response.text
    assert graph.reverted == [copy_id(PLACE.id, "case-a")]
    assert working_set.removed == graph.reverted
    body = response.json()
    assert body["copies_kept"] == 3, body  # Uppingham, Oakham, Exton; not the SECRET depot
    assert body["said"] == (
        "3 places stay in this dataset: a case's own load, link or confirmation rests on them."
    )
    # The link was read in the layer of every case reading the dataset, as the dataset's unit.
    assert {"case-a", "layer-inv-1"} <= set(graph.expanded_as[-1].datasets or [])
    assert all(graph.nodes[n.id].provenance.gazetteer == GAZ for n in kept.values())
    assert store.added == {}
    assert audit.records[-1]["action"] == "remove_dataset_gazetteer"


def test_a_rebuild_never_writes_over_what_a_case_asserted(world: World) -> None:
    """Item 1: a copy the case has written to is the case's data now."""
    graph, *_ = world
    _put()
    copy = graph.nodes[copy_id(PLACE.id, "case-a")]
    copy.properties["name"] = "Cranford (the case's spelling)"
    copy.provenance.sources.append(SourceRef(document_id="case-load", locator="row 1",
                                             excerpt_hash=""))  # fmt: skip
    before = len(graph.written)
    _put()
    assert len(graph.written) == before
    assert graph.nodes[copy.id].properties["name"] == "Cranford (the case's spelling)"


def test_the_addition_is_the_dataset_s_so_every_case_reading_it_sees_it(world: World) -> None:
    graph, datasets, *_ = world
    datasets.cases["inv-2"] = ["case-a"]
    _put()
    assert _listing("inv-2")["gazetteers"][0]["added"] is True
    _delete()
    assert _listing("inv-1")["gazetteers"][0]["added"] is False


def test_a_failed_copy_again_keeps_the_earlier_addition(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _graph, _datasets, store, *_ = world
    _put()

    async def fails(*_args: Any, **_kwargs: Any) -> list[str]:
        raise RuntimeError("the store went away")

    monkeypatch.setattr("services.api.case_gazetteers.copy_places", fails)
    with pytest.raises(RuntimeError):
        _put()
    assert list(store.added) == [("case-a", GAZ)]


async def test_a_rebuild_refreshes_each_dataset_and_drops_one_no_longer_there(
    world: World,
) -> None:
    from services.api.case_gazetteers import AddedGazetteer, refresh_cases

    graph, datasets, store, *_ = world
    for held in ("case-a", "deleted-ds"):
        await store.add(AddedGazetteer(case_dataset=held, gazetteer=GAZ, added_in=held,
                                       added_by="author-1", added_at=NOW))  # fmt: skip
    await refresh_cases(graph, load_uk_le_scheme(), store, datasets, GAZ)
    assert {w.datasets[0] for w in graph.written} == {"case-a"}
    assert list(store.added) == [("case-a", GAZ)]


def test_removing_a_gazetteer_the_dataset_never_took_is_refused(world: World) -> None:
    graph, *_ = world
    assert _delete().status_code == 404
    assert graph.reverted == []
