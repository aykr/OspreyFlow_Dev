"""ADR-099 Amendment 15 (the owner's ruling of 7 November 2026 on corrections): in a case reading a
composite, a correction of a member's link is refused, in words ("correct this in a case that
reads that dataset"), so no member ever changes. A correction hides the old element from every
reader, and a composite cannot hide a member's element from its own readers alone.

Two call sites, each driven for real, each red before the refusal: `LinkChangeService.change`
(`POST .../links/{edge}/change`) here, and replacing or removing an entity's picture
(`EntityPictureService`) against ArcadeDB in `test_composite_writes_live.py`. The control: the
composite's own link (written in the case) may still be corrected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.dataset_scope import (
    CorrectionInCompositeError,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.link_changes import LinkChangeRequest, LinkChangeService
from services.api.working_set.service import WorkingSetService

from schemas.domain import (
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .test_link_changes import (
    ONTOLOGY,
    InMemoryChanges,
    MovedNotes,
    SupersedingGraph,
    _edge,
    _node,
)
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

CASE = "case-1"  # the id `_Investigations.create` gives the first case
MEMBER, OTHER, BOTH = "member", "other-member", "both"
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


def _dataset(dataset_id: str, **kind: object) -> Dataset:
    return Dataset(
        id=dataset_id,
        name=dataset_id,
        owning_unit="unit-1",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="seed",
        **kind,  # type: ignore[arg-type]
    )


async def _in_the_composite_case() -> tuple[LinkChangeService, SupersedingGraph, Principal]:
    """The service as the Conduit builds it (over the stamping graph), the case reading the
    composite, with a member's link `e1` and the composite's own link `own`."""
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    await store.set_for_case(CASE, [BOTH], ANALYST, case_name="Both")
    principal = await scope_to_case(ANALYST, CASE, store)
    working = FakeWorkingSetStore()
    ends = [_node("a").model_copy(update={"datasets": [MEMBER]})]
    ends.append(_node("b").model_copy(update={"datasets": [MEMBER]}))
    await working.add_nodes(CASE, ends)
    links = [
        _edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]}),
        _edge("own", "a", "b").model_copy(update={"datasets": [BOTH]}),
    ]
    await working.add_edges(CASE, links)
    graph = SupersedingGraph({e.id for e in links})
    stamped = stamping(graph)
    service = LinkChangeService(
        InMemoryChanges(), WorkingSetService(stamped, working, SCHEME), stamped, ONTOLOGY,
        MovedNotes(),
    )  # fmt: skip
    return service, graph, principal


async def test_a_members_link_is_not_corrected_in_a_composite_case() -> None:
    service, graph, principal = await _in_the_composite_case()
    with pytest.raises(CorrectionInCompositeError, match="correct this in a case that reads"):
        await service.change(
            CASE, "e1", principal, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
        )
    assert graph.superseded == []


async def test_the_composites_own_link_may_still_be_corrected() -> None:
    service, graph, principal = await _in_the_composite_case()
    await service.change(
        CASE, "own", principal, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
    )
    assert [old for old, _ in graph.superseded] == ["own"]


# --- node corrections, and the last word in the stamping graph (the fourth review) ------------


ROLED = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return ROLED


class _NodeGraph(FakeGraphPort):
    """Holds one member's node and records every correction it is asked to write."""

    def __init__(self, node: Node) -> None:
        super().__init__(Subgraph(nodes=[node], edges=[]))
        self.superseded: list[str] = []

    async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: Any) -> str:
        self.superseded.append(node_id)
        return replacement.id


def _member_node(state: ProvenanceState) -> Node:
    return _node("p1").model_copy(
        update={
            "datasets": [MEMBER],
            "provenance": Provenance(
                state=state,
                sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
                first_seen=datetime(2026, 1, 1, tzinfo=UTC),
                extraction_confidence=0.9 if state is ProvenanceState.INFERRED else None,
            ),
        }
    )


async def _composite_store() -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    return store


async def _post(path: str, graph: Any, overrides: dict[Any, Any]) -> Any:
    """`path` under a case reading the composite, through the real `get_principal` (so the case is
    in scope as in a deployment), with the stamping graph over `graph`."""
    from fastapi.testclient import TestClient
    from services.api.app import app, get_audit, get_graph, get_investigations

    from .test_analyst_layer import _Audit, _Investigations

    store = await _composite_store()
    investigations = _Investigations()
    case = await investigations.create(ROLED, name="Both")
    await store.set_for_case(case.id, [BOTH], ROLED, case_name="Both")
    saved = {k: getattr(app.state, k, None) for k in ("principal_resolver", "datasets")}
    app.state.principal_resolver = _Resolver()
    app.state.datasets = store
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_graph] = lambda: stamping(graph)
    for dependency, value in overrides.items():
        app.dependency_overrides[dependency] = value
    try:
        http = TestClient(app, headers={"Authorization": "Bearer token"})
        return http.post(path.format(case=case.id), json={"reason": "Told so", "type": "FAMILY_OF"})
    finally:
        app.dependency_overrides.clear()
        for key, value in saved.items():
            setattr(app.state, key, value)


@pytest.mark.parametrize(
    ("action", "state"),
    [("confirm", ProvenanceState.INFERRED), ("retract", ProvenanceState.ASSERTED)],
)
async def test_a_members_node_is_neither_confirmed_nor_retracted_in_a_composite_case(
    action: str, state: ProvenanceState
) -> None:
    """`POST .../nodes/{node}/confirm` and `/retract` answer 409 `correct_in_member_case`, in
    words, and write nothing."""
    from services.api.app import get_judgements_store

    graph = _NodeGraph(_member_node(state))
    answer = await _post(
        f"/v1/investigations/{{case}}/nodes/p1/{action}",
        graph,
        {get_judgements_store: lambda: object()},
    )
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "correct_in_member_case"
    assert "correct this in a case that reads that dataset" in answer.json()["detail"]
    assert graph.superseded == []


async def test_the_link_change_is_refused_by_the_last_word_with_the_services_check_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Must-fix 3: the stamping graph's `supersede_edge` refuses on its own. With the link-change
    service's own check planted out, the route still answers 409 and nothing is superseded."""
    from services.api import link_changes
    from services.api.app import get_link_changes, get_valkey

    async def not_checked(datasets: Any) -> None:
        return None

    monkeypatch.setattr(link_changes, "refuse_correcting_a_member", not_checked)
    service, graph, _principal = await _in_the_composite_case()
    set_case_datasets(None)
    member_link = _edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})

    async def stored(edge_ids: Any, principal: Any) -> list[Any]:
        return [member_link] if "e1" in edge_ids else []

    # The store's own answer, which the last word reads: the link is the member's.
    monkeypatch.setattr(graph, "get_edges", stored)
    answer = await _post(
        "/v1/investigations/{case}/links/e1/change",
        graph,
        {get_link_changes: lambda: service, get_valkey: lambda: object()},
    )
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "correct_in_member_case"
    assert graph.superseded == []


async def test_supersede_node_has_the_last_word() -> None:
    """The stamping graph's `supersede_node` refuses a member's node in a composite case, whatever
    the caller checked first; outside a case it passes the correction through."""
    store = await _composite_store()
    await store.set_for_case(CASE, [BOTH], ANALYST, case_name="Both")
    graph = _NodeGraph(_member_node(ProvenanceState.INFERRED))
    stamped = stamping(graph)
    replacement = _write_of(_member_node(ProvenanceState.ASSERTED))
    await scope_to_case(ANALYST, CASE, store)
    with pytest.raises(CorrectionInCompositeError):
        await stamped.supersede_node("p1", replacement, "tx")
    set_case_datasets(None)
    await stamped.supersede_node("p1", replacement, "tx")
    assert graph.superseded == ["p1"]


async def test_an_alert_closed_as_a_true_positive_on_a_members_node_is_refused_before_any_write() -> (
    None
):
    """A true positive confirms the alert's node: on a member's node in a composite case the close
    is refused before its transaction begins, so no half-done close (the alert keeps its state)."""
    from services.api import alert_queue
    from services.api.alerts import Alert, AlertMode

    class _Store:
        def __init__(self) -> None:
            self.triaged: list[object] = []

        async def set_queue_triage(self, *args: object, **kwargs: object) -> object:
            self.triaged.append(kwargs)
            return object()

    store = await _composite_store()
    await store.set_for_case(CASE, [BOTH], ANALYST, case_name="Both")
    node = _member_node(ProvenanceState.INFERRED)
    graph = _NodeGraph(node)
    alerts = _Store()
    alert = Alert(
        id="al-1",
        rule_id="r-1",
        owner_id=ANALYST.id,
        mode=AlertMode.FULL,
        referent_node_ids=["p1"],
        investigation_id=CASE,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        alert_node_id="p1",
    )
    member = await scope_to_case(ANALYST, CASE, store)
    with pytest.raises(CorrectionInCompositeError):
        await alert_queue._close(  # noqa: SLF001
            alerts,  # type: ignore[arg-type]
            stamping(graph),
            CASE,
            alert,
            {"p1": node},
            member,
            disposition="true_positive",
            reason="Seen it",
            expect=["claimed"],
        )
    assert alerts.triaged == [] and graph.superseded == []


def _write_of(node: Node) -> NodeWrite:
    return NodeWrite(
        id="p1-next",
        type=node.type,
        properties=node.properties,
        provenance=node.provenance,
        handling=node.handling,
        created_by=ANALYST.id,
        created_at=datetime(2026, 11, 7, tzinfo=UTC),
    )
