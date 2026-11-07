"""A composite is read-only for now (ADR-099 Amendments 14 and 15; the owner's ruling of 7 November
2026). A case reading a composite reads its members and keeps its own analyst layer; every other
write in it, and every write into a composite's id, is refused in words: 409 `composite_read_only`,
"do this in a case that reads that dataset", before anything is written.

Each write path is driven at its real call site, red with its refusal planted out:

- node corrections over HTTP (`nodes/{node}/confirm`, `/retract`), and the 404 for a node the
  reader cannot see, which must not become a 409;
- a link change (`LinkChangeService.change`, and the stamping graph's last word over HTTP);
- an alert closed as a true positive, refused before its transaction;
- accepting and rejecting a finding (`review.accept_candidate`, `reject_candidate`: every accept
  path's shared write), and a finding the reader cannot read still answering not found;
- email extraction (`EmailExtractionService.extract`), with nothing written and nothing stored;
- the case's loading routes (`ingest/recipes/{recipe}/run`) and the Studio's own routes of a
  composite (`POST /v1/datasets/{dataset}/sources`), with a non-member still answered 404;
- the stamping graph's last word: a write naming no dataset in a composite case, and one naming a
  composite's id as the Studio would;
- and what still works: an entity marked by hand and a manual link, into the case's layer.

Pictures (ArcadeDB) are in `test_composite_writes_live.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api import dataset_scope
from services.api.dataset_scope import (
    CompositeReadOnlyError,
    DatasetStampingGraph,
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import COMPOSITE, Dataset, InMemoryDatasetStore
from services.api.link_changes import LinkChangeRequest, LinkChangeService
from services.api.review import ExtractionCandidateNotFoundError, accept_candidate, reject_candidate
from services.api.working_set.service import WorkingSetService
from services.extract.candidates import ExtractionCandidate

from schemas.domain import (
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .test_email_extraction import (
    ONTOLOGY as FULL_ONTOLOGY,
)
from .test_email_extraction import (
    FakeRecogniser,
    FixedModel,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
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
from .working_set.test_visible_link import SCHEME, edge, node

CASE = "case-1"  # the id `_Investigations.create` gives the first case
MEMBER, OTHER, BOTH = "member", "other-member", "both"
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
ROLED = ANALYST.model_copy(update={"roles": ["analyst", "data_engineer", "source_author"]})
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
WORDS = "do this in a case that reads that dataset"


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


async def _composite_store() -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    store.add(_dataset(MEMBER))
    store.add(_dataset(OTHER))
    store.add(_dataset(BOTH, kind=COMPOSITE, members=[MEMBER, OTHER]))
    return store


async def _in_the_composite_case() -> tuple[InMemoryDatasetStore, Principal]:
    store = await _composite_store()
    await store.set_for_case(CASE, [BOTH], ANALYST, case_name="Both")
    return store, await scope_to_case(ANALYST, CASE, store)


def _planted_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15: the refusal planted out wherever it lives (each service's call, and the stamping
    graph's last word), as the code stood before the ruling."""

    async def allowed(*args: Any, **kwargs: Any) -> None:
        return None

    import services.api.alert_queue as alert_queue
    import services.api.app as app_module
    import services.api.email_extraction as email_extraction
    import services.api.link_changes as link_changes
    import services.api.review as review

    for module in (dataset_scope, alert_queue, email_extraction, link_changes, review):
        monkeypatch.setattr(module, "refuse_in_a_composite_case", allowed)
    monkeypatch.setattr(app_module, "refuse_writing_a_node_in_a_composite_case", allowed)
    monkeypatch.setattr(app_module, "refuse_in_a_composite_case", allowed)

    async def no_composites(self: Any, dataset_ids: Any) -> set[str]:
        return set()

    monkeypatch.setattr(InMemoryDatasetStore, "composites_among", no_composites)
    monkeypatch.setattr(DatasetStampingGraph, "_refuse_into_a_composite", allowed)


# --- node corrections, over HTTP ----------------------------------------------------------------


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return ROLED


class _NodeGraph(FakeGraphPort):
    """Holds the given nodes and records every correction it is asked to write."""

    def __init__(self, *nodes: Node) -> None:
        super().__init__(Subgraph(nodes=list(nodes), edges=[]))
        self.superseded: list[str] = []

    async def supersede_node(self, node_id: str, replacement: NodeWrite, tx: Any) -> str:
        self.superseded.append(node_id)
        return replacement.id


def _member_node(state: ProvenanceState, node_id: str = "p1") -> Node:
    return _node(node_id).model_copy(
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


async def _http(
    method: str,
    path: str,
    graph: Any,
    overrides: dict[Any, Any],
    *,
    member: bool = True,
    body: dict[str, Any] | None = None,
) -> Any:
    """`path` under a case reading the composite, through the real `get_principal` (so the case is
    in scope as in a deployment). With `member=False` the caller holds no level on the case."""
    from fastapi.testclient import TestClient
    from services.api.app import app, get_audit, get_graph, get_investigations

    from .test_analyst_layer import _Audit, _Investigations

    store = await _composite_store()
    investigations = _Investigations()
    owner = ROLED if member else ROLED.model_copy(update={"id": "someone-else"})
    case = await investigations.create(owner, name="Both")
    await store.set_for_case(case.id, [BOTH], owner, case_name="Both")
    saved = {
        k: getattr(app.state, k, None) for k in ("principal_resolver", "datasets", "investigations")
    }
    app.state.principal_resolver = _Resolver()
    app.state.datasets = store
    app.state.investigations = investigations
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_audit] = _Audit
    app.dependency_overrides[get_graph] = lambda: stamping(graph, registry=store)
    for dependency, value in overrides.items():
        app.dependency_overrides[dependency] = value
    try:
        http = TestClient(app, headers={"Authorization": "Bearer token"})
        return http.request(
            method,
            path.format(case=case.id, dataset=BOTH),
            json=body if body is not None else {},
        )
    finally:
        app.dependency_overrides.clear()
        for key, value in saved.items():
            setattr(app.state, key, value)


def _judgements() -> dict[Any, Any]:
    from services.api.app import get_judgements_store

    return {get_judgements_store: lambda: object()}


@pytest.mark.parametrize(
    ("action", "state"),
    [("confirm", ProvenanceState.INFERRED), ("retract", ProvenanceState.ASSERTED)],
)
async def test_a_node_is_neither_confirmed_nor_retracted_in_a_composite_case(
    action: str, state: ProvenanceState
) -> None:
    graph = _NodeGraph(_member_node(state))
    answer = await _http(
        "POST", f"/v1/investigations/{{case}}/nodes/p1/{action}", graph, _judgements()
    )
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "composite_read_only"
    assert WORDS in answer.json()["detail"]
    assert graph.superseded == []


async def test_the_node_check_fails_with_the_refusal_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planted_out(monkeypatch)
    graph = _NodeGraph(_member_node(ProvenanceState.INFERRED))
    try:
        await _http("POST", "/v1/investigations/{case}/nodes/p1/confirm", graph, _judgements())
    except AttributeError:
        pass  # the confirmation was written; only the judgement stub stops the route after it
    assert graph.superseded == ["p1"]


async def test_a_node_the_reader_cannot_see_is_not_found_not_refused() -> None:
    """The refusal comes after the read, so it says nothing of a node the reader cannot see."""
    graph = _NodeGraph()
    graph._hidden_node_ids = {"hidden"}  # noqa: SLF001 (a node this reader may not see)
    answer = await _http(
        "POST", "/v1/investigations/{case}/nodes/hidden/confirm", graph, _judgements()
    )
    assert answer.status_code == 404, answer.text
    assert graph.superseded == []


# --- a link change, in the service and by the last word -----------------------------------------


async def _link_change_service() -> tuple[LinkChangeService, SupersedingGraph]:
    working = FakeWorkingSetStore()
    ends = [_node(n).model_copy(update={"datasets": [MEMBER]}) for n in ("a", "b")]
    await working.add_nodes(CASE, ends)
    links = [_edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})]
    await working.add_edges(CASE, links)
    graph = SupersedingGraph({e.id for e in links})
    stamped = stamping(graph)
    service = LinkChangeService(
        InMemoryChanges(), WorkingSetService(stamped, working, SCHEME), stamped, ONTOLOGY,
        MovedNotes(),
    )  # fmt: skip
    return service, graph


async def test_a_link_is_not_changed_in_a_composite_case() -> None:
    _, principal = await _in_the_composite_case()
    service, graph = await _link_change_service()
    with pytest.raises(CompositeReadOnlyError, match=WORDS):
        await service.change(
            CASE, "e1", principal, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
        )
    assert graph.superseded == []


async def test_the_stamping_graphs_last_word_refuses_a_link_change_over_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the service's own check planted out, `supersede_edge` still refuses: 409."""
    from services.api import link_changes
    from services.api.app import get_link_changes, get_valkey

    async def not_checked() -> None:
        return None

    monkeypatch.setattr(link_changes, "refuse_in_a_composite_case", not_checked)
    service, graph = await _link_change_service()
    member_link = _edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})

    async def stored(edge_ids: Any, principal: Any) -> list[Any]:
        return [member_link] if "e1" in edge_ids else []

    monkeypatch.setattr(graph, "get_edges", stored)
    answer = await _http(
        "POST",
        "/v1/investigations/{case}/links/e1/change",
        graph,
        {get_link_changes: lambda: service, get_valkey: lambda: object()},
        body={"reason": "Told so", "type": "FAMILY_OF"},
    )
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "composite_read_only"
    assert graph.superseded == []


async def test_supersede_node_has_the_last_word() -> None:
    _, _principal = await _in_the_composite_case()
    graph = _NodeGraph(_member_node(ProvenanceState.INFERRED))
    stamped = stamping(graph)
    with pytest.raises(CompositeReadOnlyError):
        await stamped.supersede_node("p1", _write("p1-next"), "tx")
    set_case_datasets(None)
    await stamped.supersede_node("p1", _write("p1-next"), "tx")  # outside a case: through
    assert graph.superseded == ["p1"]


# --- an alert closed as a true positive -----------------------------------------------------------


async def _close(principal: Principal) -> tuple[list[object], _NodeGraph]:
    from services.api import alert_queue
    from services.api.alerts import Alert, AlertMode

    class _Store:
        def __init__(self) -> None:
            self.triaged: list[object] = []

        async def set_queue_triage(self, *args: object, **kwargs: object) -> object:
            self.triaged.append(kwargs)
            return object()

    member_node = _member_node(ProvenanceState.INFERRED)
    graph = _NodeGraph(member_node)
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
    await alert_queue._close(  # noqa: SLF001
        alerts,  # type: ignore[arg-type]
        stamping(graph),
        CASE,
        alert,
        {"p1": member_node},
        principal,
        disposition="true_positive",
        reason="Seen it",
        expect=["claimed"],
    )
    return alerts.triaged, graph


async def test_an_alert_closed_as_a_true_positive_is_refused_before_any_write() -> None:
    _, principal = await _in_the_composite_case()
    with pytest.raises(CompositeReadOnlyError):
        await _close(principal)


async def test_the_close_check_fails_with_the_refusal_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planted_out(monkeypatch)
    _, principal = await _in_the_composite_case()
    triaged, graph = await _close(principal)
    assert graph.superseded == ["p1"] and len(triaged) == 1


# --- accepting and rejecting a finding --------------------------------------------------------


async def _a_finding(principal: Principal) -> tuple[InMemoryCandidates, str]:
    candidates = InMemoryCandidates()
    (pending,) = await candidates.store(
        [
            ExtractionCandidate(
                id="cand-1",
                document_id="doc-1",
                entity_type="Person",
                properties={"family_name": "MERCER", "given_names": "Dana"},
                confidence=0.9,
                model="local-model",
                locator="char span 0-11",
                excerpt_hash="",
                handling=HANDLING,
            )
        ],
        principal,
    )
    return candidates, pending.id


@pytest.mark.parametrize("decide", ["accept", "reject"])
async def test_a_finding_is_neither_accepted_nor_rejected_in_a_composite_case(decide: str) -> None:
    """`accept_candidate` is the write every accept path shares (a document's, an email's, a
    question's); `reject_candidate` every reject."""
    _, principal = await _in_the_composite_case()
    candidates, finding = await _a_finding(principal)
    graph = WritingGraph()
    with pytest.raises(CompositeReadOnlyError):
        if decide == "accept":
            await accept_candidate(candidates, stamping(graph), finding, principal)  # type: ignore[arg-type]
        else:
            await reject_candidate(candidates, finding, principal)  # type: ignore[arg-type]
    assert graph.nodes == {}
    assert candidates.records[finding].status.value == "pending"


async def test_a_finding_the_reader_cannot_read_is_not_found_not_refused() -> None:
    _, principal = await _in_the_composite_case()
    elsewhere = Principal(id="x", clearance="OFFICIAL", org_unit="unit-9")
    candidates, finding = await _a_finding(elsewhere)
    with pytest.raises(ExtractionCandidateNotFoundError):
        await accept_candidate(candidates, stamping(WritingGraph()), finding, principal)  # type: ignore[arg-type]


async def test_the_finding_check_fails_with_the_refusal_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planted_out(monkeypatch)
    _, principal = await _in_the_composite_case()
    candidates, finding = await _a_finding(principal)
    graph = WritingGraph()
    await accept_candidate(candidates, stamping(graph), finding, principal)  # type: ignore[arg-type]
    assert len(graph.nodes) == 1


# --- extraction ---------------------------------------------------------------------------------


async def _extract(principal: Principal) -> tuple[WritingGraph, InMemoryCandidates]:
    from services.api.email_extraction import EmailExtractionService

    working = FakeWorkingSetStore()
    people = [node(n).model_copy(update={"datasets": [MEMBER]}) for n in ("a", "b")]
    await working.add_nodes(CASE, people)
    await working.add_edges(CASE, [edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})])
    graph = WritingGraph()
    stamped = stamping(graph)
    candidates = InMemoryCandidates()
    service = EmailExtractionService(
        WorkingSetService(stamped, working, SCHEME),
        RecordingAnalytics([_event("ev-1").model_copy(update={"investigation_scope": CASE})]),  # type: ignore[arg-type]
        stamped,
        FULL_ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        FixedModel({"Person": [{"family_name": "MERCER", "confidence": 0.9}]}),  # type: ignore[arg-type]
        "local-model",
        recogniser=FakeRecogniser(),
    )
    await service.extract(CASE, "e1", "ev-1", principal)
    return graph, candidates


async def test_an_email_is_not_extracted_in_a_composite_case() -> None:
    _, principal = await _in_the_composite_case()
    with pytest.raises(CompositeReadOnlyError):
        await _extract(principal)


async def test_the_extraction_check_fails_with_the_refusal_planted_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planted_out(monkeypatch)
    _, principal = await _in_the_composite_case()
    graph, candidates = await _extract(principal)
    assert graph.nodes and candidates.records


# --- the case's loading routes and the Studio's -----------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/investigations/{case}/ingest/recipes/r-1/run"),
        ("PATCH", "/v1/investigations/{case}/ingest/recipes/r-1/schedule"),
        ("POST", "/v1/investigations/{case}/ingest/source-files"),
        ("POST", "/v1/datasets/{dataset}/sources"),
    ],
)
async def test_a_composite_is_not_loaded_run_or_scheduled(method: str, path: str) -> None:
    answer = await _http(method, path, FakeGraphPort(Subgraph(nodes=[], edges=[])), {})
    assert answer.status_code == 409, answer.text
    assert answer.json()["error"] == "composite_read_only"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/investigations/{case}/ingest/recipes/r-1/run"),
        ("POST", "/v1/datasets/{dataset}/sources"),
    ],
)
async def test_the_loading_check_fails_with_the_refusal_planted_out(
    method: str, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the refusal planted out of the routes' dependency, the route goes on to its own work
    (and fails there, on this harness's missing stores): never the read-only answer."""
    _planted_out(monkeypatch)
    try:
        answer = await _http(method, path, FakeGraphPort(Subgraph(nodes=[], edges=[])), {})
    except Exception:  # noqa: BLE001 - the route reached past the refusal into its own work
        return
    assert answer.status_code != 409 or answer.json().get("error") != "composite_read_only"


@pytest.mark.parametrize(
    "path",
    ["/v1/investigations/{case}/ingest/recipes/r-1/run", "/v1/datasets/{dataset}/sources"],
)
async def test_someone_the_case_is_not_for_is_answered_404_not_409(path: str) -> None:
    answer = await _http(
        "POST", path, FakeGraphPort(Subgraph(nodes=[], edges=[])), {}, member=False
    )
    assert answer.status_code == 404, answer.text


# --- the stamping graph's last word -----------------------------------------------------------


async def test_a_write_naming_no_dataset_in_a_composite_case_is_refused() -> None:
    store, _ = await _in_the_composite_case()
    graph = WritingGraph()
    stamped = stamping(graph, registry=store)
    tx = await stamped.begin_transaction()
    with pytest.raises(CompositeReadOnlyError):
        await stamped.upsert_nodes([_write("p9")], tx)
    assert graph.nodes == {}


async def test_a_write_into_a_composites_id_is_refused_as_the_studio_would_make_it() -> None:
    """The Studio reaches a dataset with no case (`scope_to_dataset`); a write stamped with a
    composite's id is refused by the dataset store's answer."""
    store = await _composite_store()
    set_case_datasets([BOTH])  # as `scope_to_dataset` holds a request of the composite
    graph = WritingGraph()
    stamped = stamping(graph, registry=store)
    tx = await stamped.begin_transaction()
    with pytest.raises(CompositeReadOnlyError):
        await stamped.upsert_nodes([_write("p9")], tx)
    assert graph.nodes == {}


async def test_the_last_word_fails_with_it_planted_out(monkeypatch: pytest.MonkeyPatch) -> None:
    _planted_out(monkeypatch)
    store, _ = await _in_the_composite_case()
    graph = WritingGraph()
    stamped = stamping(graph, registry=store)
    tx = await stamped.begin_transaction()
    await stamped.upsert_nodes([_write("p9")], tx)
    await stamped.commit_transaction(tx)
    assert "p9" in graph.nodes


# --- what still works: the case's own analyst layer -------------------------------------------


async def test_a_mark_made_by_hand_in_a_composite_case_goes_into_its_layer() -> None:
    from services.api.document_reader import Designation, DocumentReaderService
    from services.api.email_extraction import email_document_id

    from .test_case_writes import _document
    from .test_email_extraction import TEXT

    store, principal = await _in_the_composite_case()
    layer = await store.layer_of_case(CASE)
    doc = _document(email_document_id("ev-1")).model_copy(update={"datasets": [MEMBER]})
    working = FakeWorkingSetStore()
    people = [node(n).model_copy(update={"datasets": [MEMBER]}) for n in ("a", "b")]
    await working.add_nodes(CASE, [*people, doc])
    await working.add_edges(CASE, [edge("e1", "a", "b").model_copy(update={"datasets": [MEMBER]})])
    written = WritingGraph()
    graph = stamping(written, registry=store)
    reader = DocumentReaderService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_event("ev-1").model_copy(update={"investigation_scope": CASE})]),  # type: ignore[arg-type]
        graph,
        InMemoryCandidates(),  # type: ignore[arg-type]
    )
    start = TEXT.index("Dana MERCER")
    result = await reader.designate(
        CASE,
        doc.id,
        Designation(entity_type="Person", text="Dana MERCER", start=start, end=start + 11),
        principal,
    )
    assert written.nodes[result.node_id].datasets == [layer]


async def test_a_manual_link_in_a_composite_case_goes_into_its_layer() -> None:
    store, principal = await _in_the_composite_case()
    layer = await store.layer_of_case(CASE)
    people = [_member_node(ProvenanceState.ASSERTED, n) for n in ("n1", "n2")]
    inner = FakeGraphPort(Subgraph(nodes=people, edges=[]))
    working = FakeWorkingSetStore()
    await working.add_nodes(CASE, people)
    await WorkingSetService(stamping(inner, registry=store), working, SCHEME).manual_link(
        CASE, "n1", "n2", principal
    )
    (written,) = inner.committed_edges
    assert written.datasets == [layer]


def _write(node_id: str) -> NodeWrite:
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={"family_name": "MERCER"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime(2026, 11, 7, tzinfo=UTC),
        ),
        handling=HANDLING,
        created_by=ANALYST.id,
        created_at=datetime(2026, 11, 7, tzinfo=UTC),
    )
