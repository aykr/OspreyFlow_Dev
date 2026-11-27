"""What each route **publishes** when an add is made by a writer who may not read a drawn item's
source document (ADR-143 Amendment 8 item 5; slice GG4b, a security part; rules 3 and 4), through
the real app over `board_fakes.BoardGraph`, with the message each route puts on the case's channel
read back as a socket reads it.

**A** is Alice (SECRET), who draws an item and a link citing document **D**; **B** is Bob (OFFICIAL,
an Editor of the case), who may not read D and who puts the item on the canvas by each route there is.

The writer's own answer has no D. What is published, which each recipient's socket projects for its
own reader, keeps D as stored: otherwise B's view would be pushed to everyone as the item itself,
and a reader who may read D would be sent the item without it.

What fails if the rule is wrong (shown red with the fault planted,
`process/lanes/v062/GG4b_RED_RECORD.md`):

- a route publishing the writer's view: red with `publish_delta` publishing what it is given;
- an add the Conduit wrote that brings a stored drawn link back (`add_written`: an upload, an
  accepted finding, an email made a Document, a picture) publishing the writer's view of that link;
- an add's answer, held in a route's own result, losing what is to be published.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import alert_queue
from services.api import ownership as ownership_module
from services.api.app import (
    app,
    get_alerts_store,
    get_analytics,
    get_explore,
    get_history,
    get_valkey,
)
from services.api.document_content import (
    DocumentAcceptResult,
    DocumentBulkAcceptResult,
    DocumentContentService,
    DocumentUploadResult,
)
from services.api.document_reader import DesignationResult
from services.api.email_extraction import (
    EmailAcceptResult,
    EmailDocumentsResult,
    EmailExtractionResult,
)
from services.api.entity_pictures import PictureSetResult
from services.api.history import HistoryStep
from services.api.notify import publish_delta
from services.api.questions import QuestionAccepted
from services.api.working_set.models import (
    DeltaAdd,
    DeltaSnapshot,
    WorkingSetDelta,
    decode_delta,
)

from schemas.domain import AuditStub, Edge, Handling, Node, Principal, Provenance, SourceRef

from .test_boards import (  # noqa: F401 (`world` is a fixture)
    PEOPLE,
    SCHEME,
    UNIT,
    K,
    _as,
    _board,
    _item,
    _link,
    world,
)

D = "doc-sealed-statement"
NINO = "CE123456A"
WHEN = datetime(2026, 11, 1, tzinfo=UTC)
BASE = f"/v1/investigations/{K}"


class _Channel:
    """The case's channel: every message published, as the sockets would be handed it."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def publish(self, channel: str, message: str) -> int:
        assert channel == f"ws:{K}:notify"
        self.messages.append(message)
        return 1

    def deltas(self) -> list[WorkingSetDelta]:
        """Each message decoded as the socket decodes it."""
        import json

        return [decode_delta(json.loads(m)) for m in self.messages]


class _History:
    def __init__(self) -> None:
        self.step: HistoryStep | None = None

    async def record_step(self, investigation_id: str, **kwargs: Any) -> object:
        return object()

    async def get_step(self, investigation_id: str, step_id: str) -> HistoryStep:
        assert self.step is not None
        return self.step


def _document() -> Node:
    return Node(
        id=D,
        type="Document",
        properties={"title": "Sealed statement"},
        provenance=Provenance(
            state="asserted",  # type: ignore[arg-type]
            sources=[SourceRef(document_id="files/s.txt", locator="whole", excerpt_hash="")],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="OFFICIAL-SENSITIVE",
            handling_code="P",
            originator=UNIT,
            owning_unit=UNIT,
        ),
        audit=AuditStub(created_at=WHEN, created_by="eng"),
        datasets=["src"],
    )


@pytest.fixture
def case(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[SimpleNamespace]:
    """Alice has drawn a person and a link from them to the loaded Mercer, each citing D. Nothing
    is on the working set yet, and nothing has been published."""
    monkeypatch.setitem(
        PEOPLE,
        "bob",
        PEOPLE["bob"].model_copy(
            update={
                "roles": [
                    "analyst",
                    "right:trace_ownership",
                    "right:triage_alerts",
                    "right:read_alert_queue",
                ]
            }
        ),
    )
    world.graph._graph_nodes[D] = _document()
    board = _board(start="selection", node_ids=["p-loaded"])
    node_id = _item(
        board, source_document=D, properties={"family_name": "Tall", "nino": NINO}
    )["element_id"]
    linked = _link(board, node_id, "p-loaded", source_document=D)
    assert linked.status_code == 201, linked.text
    link_id = linked.json()["element_id"]
    shared = _as("alice").post(f"{BASE}/boards/{board}/share")
    assert shared.status_code == 200, shared.text

    channel, history = _Channel(), _History()
    app.dependency_overrides[get_valkey] = lambda: channel
    app.dependency_overrides[get_history] = lambda: history
    held = SimpleNamespace(
        world=world, board=board, node_id=node_id, link_id=link_id,
        channel=channel, history=history,
    )  # fmt: skip
    try:
        yield held
    finally:
        app.dependency_overrides.clear()


def _stored(case: SimpleNamespace) -> tuple[list[Node], list[Edge]]:
    """The drawn item, the loaded node it is linked to, and the link, as the Vault holds them."""
    graph = case.world.graph
    nodes = [graph.node(case.node_id), graph.node("p-loaded")]
    return nodes, [e for e in graph.edges() if e.id == case.link_id]


def _bodies(nodes: list[Node], edges: list[Edge]) -> dict[str, Any]:
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "edges": [e.model_dump(mode="json") for e in edges],
    }


def _bob_adds(path: str, **kwargs: Any) -> Any:
    answer = _as("bob").post(f"{BASE}/{path}", **kwargs)
    assert answer.status_code in (200, 201), answer.text
    return answer


# --- each route that adds, as B ----------------------------------------------------------------


def _by_seed(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    return _bob_adds("seed", json=_bodies(*_stored(case))), {case.node_id, case.link_id}


def _by_ids(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    body = {"node_ids": [case.node_id, "p-loaded"], "link_ids": [case.link_id]}
    return _bob_adds("working-set/add-by-ids", json=body), {case.node_id, case.link_id}


def _by_expansion(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    nodes, edges = _stored(case)
    case.world.graph.expand_result = case.world.graph.expand_result.model_copy(
        update={"nodes": nodes, "edges": edges}
    )
    body = {"request": {"node_ids": ["p-loaded"]}}
    return _bob_adds("expand", json=body), {case.node_id, case.link_id}


def _by_links_among(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    nodes, _ = _stored(case)
    _bob_adds("seed", json=_bodies(nodes, []))
    case.channel.messages.clear()
    return _bob_adds("links-among", json={}), {case.link_id}


def _by_identifiers(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    _bob_adds("seed", json=_bodies([case.world.graph.node("p-loaded")], []))
    case.channel.messages.clear()
    body = {"identifiers": [NINO], "confirm": True, "with_links": True}
    return _bob_adds("working-set/add-by-identifiers", json=body), {case.node_id, case.link_id}


class _Explore:
    """What a starter question or a shared pair matched, read from the graph as the person asking,
    as `ExploreService` reads it."""

    def __init__(self, case: SimpleNamespace) -> None:
        self.case = case

    async def _read(self, principal: Principal) -> tuple[list[Node], list[Edge]]:
        graph = self.case.world.graph
        return (
            await graph.get_nodes([self.case.node_id, "p-loaded"], principal),
            await graph.get_edges([self.case.link_id], principal),
        )

    async def run_starter(
        self, principal: Principal, ontology: Any, question_id: str
    ) -> tuple[list[Node], list[Edge]]:
        return await self._read(principal)

    async def shared_pair(
        self, principal: Principal, node_id: str, other_id: str, *, edge_type: str
    ) -> tuple[list[Node], list[Edge]]:
        return await self._read(principal)


def _by_starter_question(
    case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, set[str]]:
    app.dependency_overrides[get_explore] = lambda: _Explore(case)
    return (
        _bob_adds("explore/starter-questions/q-1/run"),
        {case.node_id, case.link_id},
    )


def _by_shared_pair(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    app.dependency_overrides[get_explore] = lambda: _Explore(case)
    path = f"nodes/{case.node_id}/shared-contacts/p-loaded/canvas?edge_type=ASSOCIATE_OF"
    return _bob_adds(path), {case.node_id, case.link_id}


def _by_ownership(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    async def read_structure(
        graph: Any, node_id: str, principal: Principal, *, max_depth: int
    ) -> tuple[dict[str, Node], dict[str, Edge]]:
        nodes, edges = await _Explore(case)._read(principal)
        return {n.id: n for n in nodes}, {e.id: e for e in edges}

    monkeypatch.setattr(ownership_module, "read_structure", read_structure)
    return _bob_adds("ownership/p-loaded/canvas"), {case.node_id, case.link_id}


def _by_alert(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    async def canvas_elements(
        store: Any, graph: Any, analytics: Any, case_id: str, alert_id: str, principal: Principal
    ) -> tuple[None, list[Node], list[Edge]]:
        nodes, edges = await _Explore(case)._read(principal)
        return None, nodes, edges

    monkeypatch.setattr(alert_queue, "canvas_elements", canvas_elements)
    app.dependency_overrides[get_alerts_store] = lambda: object()
    app.dependency_overrides[get_analytics] = lambda: object()
    return _bob_adds("alert-queue/a-1/canvas"), {case.node_id, case.link_id}


def _by_restore(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    nodes, edges = _stored(case)
    case.history.step = HistoryStep(
        id="step-1", investigation_id=K, seq=1, label="seeded", created_at=WHEN,
        created_by="alice", nodes=nodes, edges=edges,
    )  # fmt: skip
    return _bob_adds("history/step-1"), {case.node_id, case.link_id}


def _upload(case: SimpleNamespace, who: str) -> Any:
    answer = _as(who).post(
        f"{BASE}/documents",
        params={"name": "note.txt", "classification": "OFFICIAL", "legal_basis": "s.29"},
        content=b"the officer's note",
    )
    assert answer.status_code in (200, 201), answer.text
    return answer


def _by_upload(case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, set[str]]:
    """An add the Conduit writes itself (`add_written`), which brings a stored drawn link back:
    the drawn person is said to hold an uploaded file, the file leaves the canvas, and B uploads
    the same file, which is the same Document."""
    state = app.state
    monkeypatch.setattr(
        app.state,
        "document_content",
        DocumentContentService(
            state.working_set, state.graph, state.media, None,  # type: ignore[arg-type]
            state.ontology, None,  # type: ignore[arg-type]
            text_model="", vision_model="", transcribe_model="", scheme=SCHEME,
        ),  # fmt: skip
        raising=False,
    )
    document_id = _upload(case, "alice").json()["document_id"]
    board = _board(start="selection", node_ids=["p-loaded", document_id])
    holder = _item(board, source_document=D)["element_id"]
    holds = _link(board, holder, document_id, type="HOLDS", source_document=D)
    assert holds.status_code == 201, holds.text
    link_id = holds.json()["element_id"]
    graph = case.world.graph
    seeded = _as("alice").post(
        f"{BASE}/seed",
        json=_bodies(
            [graph.node(holder), graph.node(document_id)],
            [e for e in graph.edges() if e.id == link_id],
        ),
    )
    assert seeded.status_code == 200, seeded.text
    removed = _as("alice").request("DELETE", f"{BASE}/nodes", json={"node_ids": [document_id]})
    assert removed.status_code == 200, removed.text
    case.channel.messages.clear()
    return _upload(case, "bob"), {link_id}


ADDS = {
    "seed": _by_seed,
    "add-by-ids": _by_ids,
    "expand": _by_expansion,
    "links-among": _by_links_among,
    "add-by-identifiers": _by_identifiers,
    "starter-question": _by_starter_question,
    "shared-pair": _by_shared_pair,
    "ownership-canvas": _by_ownership,
    "alert-canvas": _by_alert,
    "restore": _by_restore,
    "upload": _by_upload,
}


@pytest.mark.parametrize("route", ADDS)
def test_what_a_route_publishes_keeps_the_document_its_writer_may_not_read(
    route: str, case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer, cited = ADDS[route](case, monkeypatch)

    # B's own answer never names D.
    assert D not in answer.text, "the writer who may not read D is answered without it"
    # What every socket projects from holds D in both places, on each drawn element sent.
    (published,) = case.channel.deltas()
    assert isinstance(published, DeltaAdd | DeltaSnapshot)
    drawn = {
        e.id: e.provenance
        for e in [*published.nodes, *published.edges]
        if e.provenance.drawn is not None
    }
    assert set(drawn) == cited
    for element_id, provenance in drawn.items():
        assert provenance.drawn is not None
        assert provenance.drawn.source_document == D, element_id
        assert [s.document_id for s in provenance.sources] == [D], element_id


def test_a_reader_who_may_read_the_document_is_pushed_it_from_what_a_route_published(
    case: SimpleNamespace,
) -> None:
    """The end the publishing serves: B adds; A's socket sends A the document, B's does not."""
    import asyncio

    _bob_adds("seed", json=_bodies(*_stored(case)))
    (published,) = case.channel.deltas()
    service = app.state.working_set

    for_a = asyncio.run(service.project_live(K, published, PEOPLE["alice"]))
    for_b = asyncio.run(service.project_live(K, published, PEOPLE["bob"]))

    assert for_a.model_dump_json().count(D) == 4, "both places, on the node and the link"
    assert D not in for_b.model_dump_json()


# --- one publisher, whatever holds the add ------------------------------------------------------


def _writers_add() -> DeltaAdd:
    """An add as a writer who may not read the document is answered, holding what was stored."""
    provenance = Provenance(
        state="asserted",  # type: ignore[arg-type]
        sources=[SourceRef(document_id=D, locator="drawn on a board", excerpt_hash="")],
        first_seen=WHEN,
    )
    node = _document().model_copy(update={"id": "n-1", "type": "Person", "properties": {}})
    stored = DeltaAdd(seq=1, nodes=[node.model_copy(update={"provenance": provenance})])
    theirs = DeltaAdd(seq=1, nodes=[node])
    return theirs.holding(stored)


#: Every result a route holds an add of the Conduit's own writing in (`add_written`), each as the
#: service builds it, and how the route takes the add out of it to publish it.
HELD_IN: dict[str, Any] = {
    "upload": lambda d: [DocumentUploadResult(document_id="x", delta=d).delta],
    "accept a document's finding": lambda d: [DocumentAcceptResult(node_id="x", delta=d).delta],
    "accept several findings": lambda d: [
        a.delta
        for a in DocumentBulkAcceptResult(
            accepted=[DocumentAcceptResult(node_id="x", delta=d)], refusals=[]
        ).accepted
    ],
    "accept a question's finding": lambda d: [QuestionAccepted(node_id="x", delta=d).delta],
    "designate in a document": lambda d: [DesignationResult(node_id="x", delta=d).delta],
    "extract an email": lambda d: [
        EmailExtractionResult(document_id="x", candidates=[], delta=d).delta
    ],
    "emails as documents": lambda d: [
        EmailDocumentsResult(written=1, without_text=0, delta=d).delta
    ],
    "accept an email's finding": lambda d: [EmailAcceptResult(node_id="x", delta=d).delta],
    "set a picture": lambda d: PictureSetResult(document_id="x", deltas=[d]).deltas,
}


@pytest.mark.parametrize("holder", HELD_IN)
async def test_an_add_held_in_a_routes_result_is_published_as_stored(holder: str) -> None:
    channel = _Channel()
    theirs = _writers_add()

    (taken,) = HELD_IN[holder](theirs)
    await publish_delta(channel, K, taken)  # type: ignore[arg-type]

    (published,) = channel.deltas()
    assert D in published.model_dump_json()
    assert D not in taken.model_dump_json(), "what the route answers never carries the stored add"
