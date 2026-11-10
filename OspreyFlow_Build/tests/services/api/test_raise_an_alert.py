"""*Raise an alert…* (`spec/06_DECISIONS.md` ADR-146 decision 7, R4), at the route: an analyst raises
an alert to their case or to the case's dataset, with its evidence. Each refusal is made before
anything is written (the recorder store is asked to save nothing), and each is red with its check
removed at the real call site (`services/api/raised_alerts.py`, `app.raise_an_alert`):

- a case the raiser may not write (a Viewer) — `test_a_case_the_raiser_may_not_write_is_refused`;
- a dataset the case does not read, a layer, or one with no home case —
  `test_a_dataset_the_case_does_not_read_or_with_no_home_case_is_refused`;
- an item the raiser may not read, answered as one that does not exist —
  `test_an_item_the_raiser_may_not_read_is_answered_as_missing`;
- a dataset alert citing a drawn item (the case's layer alone), refused at the route, not only in
  the form (ADR-146's test) — `test_a_dataset_alert_citing_a_drawn_item_is_refused_at_the_route`.

The fakes refuse what the real dependencies refuse (rule 15): the graph leaves out a node the
reader may not read, as `GraphPort.get_nodes` does; the dataset store answers only datasets it
holds, a layer by its kind, and a home case only once made.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_alerts_store,
    get_audit,
    get_datasets,
    get_graph,
    get_investigations,
    get_principal,
)
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel

from schemas.dataset_model import HomeCase
from schemas.domain import Alert, AuditStub, Node, Principal, Provenance, ProvenanceState, SourceRef
from tests.services.api.test_monitoring_routes import _Audit, _Case, _no_lifespan

NOW = datetime(2026, 11, 9, tzinfo=UTC)
CASE, HOME = "case-1", "case-home"
DATASET, LAYER, ELSEWHERE = "ds-1", "layer-1", "ds-2"
RAISER = Principal(id="raiser", clearance="OFFICIAL", org_unit="unit-a", roles=["analyst"])
VIEWER = RAISER.model_copy(update={"id": "viewer"})


def _node(node_id: str, datasets: list[str]) -> Node:
    return Node(
        id=node_id, type="Person", properties={"name": node_id}, datasets=datasets,
        provenance=Provenance(state=ProvenanceState.ASSERTED, first_seen=NOW, sources=[
            SourceRef(document_id="doc-1", locator="row 1", excerpt_hash="a" * 64)]),
        handling={"classification": "OFFICIAL", "handling_code": "P",  # type: ignore[arg-type]
                  "originator": "unit-a", "owning_unit": "unit-a"},
        audit=AuditStub(created_at=NOW, created_by="loader-1"),
    )  # fmt: skip


class _Graph:
    """`get_nodes` as the adapter answers it: a node the reader may not read is left out, and a
    node of a dataset the reader's case does not read too."""

    def __init__(self, layer: str) -> None:
        self.nodes = {"n-loaded": [DATASET], "n-drawn": [layer], "n-hidden": [DATASET]}
        self.hidden = {"n-hidden"}

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Node]:
        reach = set(principal.datasets or [])
        return [_node(i, self.nodes[i]) for i in sorted(set(node_ids))
                if i in self.nodes and i not in self.hidden and set(self.nodes[i]) & reach]  # fmt: skip

    async def get_edges(self, edge_ids: Any, principal: Principal) -> list[Any]:
        return []


async def _datasets(homes: dict[str, str]) -> tuple[InMemoryDatasetStore, str]:
    """The real in-memory dataset store: the case reads `ds-1` and has its layer; `ds-2` is a
    dataset of the deployment the case does not read; home cases as given."""
    store = InMemoryDatasetStore()
    for dataset_id in (DATASET, ELSEWHERE):
        store.add(Dataset(id=dataset_id, name=dataset_id, owning_unit="unit-a", created_at=NOW,
                          created_by="seed"))  # fmt: skip
    await store.set_for_case(CASE, [DATASET], RAISER, case_name="A case")
    layer = await store.layer_of_case(CASE)
    assert layer is not None
    for dataset_id, home in homes.items():
        await store.set_home_case(HomeCase(dataset_id=dataset_id if dataset_id != LAYER else layer,
                                           investigation_id=home, made_at=NOW, made_by="maker"))  # fmt: skip
    return store, layer


class _Store:
    def __init__(self) -> None:
        self.saved: list[Alert] = []

    async def save(self, alert: Alert, *, handlings: Any = None) -> None:
        self.saved.append(alert)


class _World:
    def __init__(self) -> None:
        self.as_ = RAISER
        self.store = _Store()
        self.audit = _Audit()
        self.cases = _Case(CASE, {RAISER.id: AccessLevel.EDITOR, VIEWER.id: AccessLevel.VIEWER})


@pytest.fixture
def world() -> Iterator[tuple[_World, TestClient]]:
    import asyncio

    w = _World()
    w.datasets, w.layer = asyncio.run(_datasets({DATASET: HOME}))
    # What the real `get_principal` gives a route in this case: the case's datasets and its layer.
    w.as_ = RAISER.model_copy(update={"datasets": [DATASET, w.layer]})
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: w.as_, get_investigations: lambda: w.cases,
        get_graph: lambda: _Graph(w.layer), get_alerts_store: lambda: w.store,
        get_audit: lambda: w.audit, get_datasets: lambda: w.datasets,
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield w, client
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous


def _raise(client: TestClient, **body: Any) -> Any:
    payload = {"title": "Same address", "reason": "Three companies at one flat", "severity": "high",
               "node_ids": ["n-loaded"], **body}  # fmt: skip
    return client.post(f"/v1/investigations/{CASE}/raised-alerts", json=payload)


def test_an_alert_is_raised_to_the_case_and_to_the_dataset(world: tuple[_World, TestClient]) -> None:
    w, client = world
    to_case = _raise(client, found_by="the query 'people at one address'")
    assert to_case.status_code == 201, to_case.text
    to_dataset = _raise(client, to="dataset", dataset_id=DATASET)
    assert to_dataset.status_code == 201, to_dataset.text
    case_alert, dataset_alert = w.store.saved
    assert (case_alert.rule_id, case_alert.investigation_id) == (f"analyst:case:{CASE}", CASE)
    assert case_alert.owner_id == RAISER.id and case_alert.severity == "high"
    assert "Found by: the query" in (case_alert.words or "")
    assert (dataset_alert.rule_id, dataset_alert.investigation_id, dataset_alert.dataset_id) == (
        f"analyst:dataset:{DATASET}", HOME, DATASET)
    assert [r["action"] for r in w.audit.records] == ["alert_raised", "alert_raised"]


def test_a_case_the_raiser_may_not_write_is_refused(world: tuple[_World, TestClient]) -> None:
    w, client = world
    w.as_ = VIEWER.model_copy(update={"datasets": [DATASET, w.layer]})
    assert _raise(client).status_code == 403
    assert _raise(client, to="dataset", dataset_id=DATASET).status_code == 403
    assert w.store.saved == []
    assert "alert_raised" not in [r["action"] for r in w.audit.records]


@pytest.mark.parametrize(
    ("dataset", "homes", "code"),
    [(ELSEWHERE, {ELSEWHERE: HOME}, "dataset_not_writable"),
     (LAYER, {LAYER: HOME}, "dataset_not_writable"),
     (DATASET, {}, "no_home_case")],
    ids=["not-read-by-the-case", "a-layer", "no-home-case"],
)  # fmt: skip
def test_a_dataset_the_case_does_not_read_or_with_no_home_case_is_refused(
    world: tuple[_World, TestClient], dataset: str, homes: dict[str, str], code: str
) -> None:
    import asyncio

    w, client = world
    store, layer = asyncio.run(_datasets(homes))
    app.dependency_overrides[get_datasets] = lambda: store
    w.layer = layer
    w.as_ = RAISER.model_copy(update={"datasets": [DATASET, layer]})
    refused = _raise(client, to="dataset", dataset_id=layer if dataset == LAYER else dataset)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == code
    assert w.store.saved == []


def test_an_item_the_raiser_may_not_read_is_answered_as_missing(world: tuple[_World, TestClient]) -> None:
    w, client = world
    hidden = _raise(client, node_ids=["n-loaded", "n-hidden"])
    missing = _raise(client, node_ids=["n-loaded", "n-never"])
    assert (hidden.status_code, hidden.text) == (missing.status_code, missing.text)
    assert hidden.status_code == 404 and w.store.saved == []


def test_a_dataset_alert_citing_a_drawn_item_is_refused_at_the_route(
    world: tuple[_World, TestClient],
) -> None:
    w, client = world
    refused = _raise(client, to="dataset", dataset_id=DATASET, node_ids=["n-loaded", "n-drawn"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "not_the_datasets_own"
    assert w.store.saved == []
    to_case = _raise(client, node_ids=["n-loaded", "n-drawn"])
    assert to_case.status_code == 201, "the same items may go to this case"
