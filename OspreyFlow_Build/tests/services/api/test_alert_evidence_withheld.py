"""An alert is withheld whole, by its links and transactions as well as its nodes (`06_DECISIONS.md`
ADR-146 decision 10, gap map G2 and G3; ADR-039's all-or-nothing; rule 3).

**G2.** The queue left out an alert whose *nodes* the reader may not see, but listed one citing a
*link* or a *transaction* they may not see, whose explanation then answered 404: a hidden element
shown to exist. **G3.** The inbox withheld an alert's referents but returned its words, which name
customers and identifiers, as stored.

These tests run the real functions against fakes that answer as the adapters do (a hidden id
is simply absent from a batched read's answer, `GraphPort.get_nodes`/`get_edges`,
`AnalyticsPort.list_events`, whose request refuses more than 200 at once) and record every read.
They prove the withholding says nothing by count, order or the work done: the reads are the same
calls with the same ids whether an alert's evidence is hidden or not, so neither their number nor
their size grows or shrinks with what is hidden (no wall-clock assertion: the identical calls are
the proof). The live counterpart, with the hidden link and transaction written as the loader writes
them, is `test_alert_evidence_withheld_live.py`.

Each was shown red against the nodes-only check before the fix (L2.8).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api import alert_queue
from services.api.alerts import QueueRow
from services.api.watch_routes import alert_to_view

from conduit_common.identity import new_id
from schemas.analytics import EventListRequest, EventListResult, EventRecord
from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Edge,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
CASE = "case-1"


_HANDLING = {"classification": "OFFICIAL", "handling_code": "P", "originator": "unit-1",
             "owning_unit": "unit-1"}  # fmt: skip


def _prov() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="row 1", excerpt_hash="a" * 64)],
        first_seen=NOW,
    )


def _node(node_id: str) -> Node:
    return Node(id=node_id, type="Person", properties={"name": f"Name of {node_id}"},
                provenance=_prov(), handling=_HANDLING,  # type: ignore[arg-type]
                audit=AuditStub(created_at=NOW, created_by="loader-1"))  # fmt: skip


def _edge(edge_id: str) -> Edge:
    return Edge(id=edge_id, type="PAID", source="n-a", target="n-b", properties={},
                provenance=_prov(), handling=_HANDLING,  # type: ignore[arg-type]
                audit=AuditStub(created_at=NOW, created_by="loader-1"))  # fmt: skip


class Recorder:
    """Every read, as (method, how many ids it asked for, the ids): what a timing would follow."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []


class Graph:
    def __init__(self, recorder: Recorder, hidden: set[str] | None = None) -> None:
        self.recorder, self.hidden = recorder, hidden or set()

    async def get_nodes(self, node_ids: Any, principal: Principal) -> list[Node]:
        ids = sorted(set(node_ids))
        self.recorder.calls.append(("get_nodes", len(ids), tuple(ids)))
        return [_node(i) for i in ids if i not in self.hidden]

    async def get_node(self, node_id: str, principal: Principal, **_: object) -> Node | None:
        self.recorder.calls.append(("get_node", 1, (node_id,)))
        return None if node_id in self.hidden else _node(node_id)

    async def edges_among(self, node_ids: Any, principal: Principal) -> list[Edge]:
        """The links among the nodes, as the reader reads them: here, every link these tests cite."""
        self.recorder.calls.append(("edges_among", len(set(node_ids)), tuple(sorted(set(node_ids)))))
        return [_edge(i) for i in ("e-1", "e-2", "e-secret") if i not in self.hidden]

    async def get_edges(self, edge_ids: Any, principal: Principal) -> list[Edge]:
        if isinstance(edge_ids, str):
            raise TypeError("edge_ids must be a sequence of ids")
        ids = sorted(set(edge_ids))
        self.recorder.calls.append(("get_edges", len(ids), tuple(ids)))
        return [_edge(i) for i in ids if i not in self.hidden]


class Analytics:
    def __init__(self, recorder: Recorder, hidden: set[str] | None = None) -> None:
        self.recorder, self.hidden = recorder, hidden or set()

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        ids = sorted(set(req.filter.event_ids))
        if not ids:
            raise AssertionError("an empty event_ids filter does not restrict: never ask with none")
        self.recorder.calls.append(
            (f"list_events:{req.filter.investigation_scope}", len(ids), tuple(ids))
        )
        events = [
            EventRecord(
                event_id=i,
                investigation_scope=req.filter.investigation_scope,
                edge_id="e-x",
                edge_type="PAID",
                source_id="n-a",
                target_id="n-b",
                occurred_at=NOW,
                properties={},
                handling=_HANDLING,
            )  # type: ignore[arg-type]  # fmt: skip
            for i in ids
            if i not in self.hidden
        ]
        return EventListResult(
            total=len(events), events=events[req.offset : req.offset + req.limit]
        )


class Store:
    def __init__(self, alerts: list[Alert]) -> None:
        self.alerts = alerts

    async def list_queue(
        self, investigation_id: str, reader: Principal, **_: object
    ) -> list[QueueRow]:
        return [QueueRow(a, "typology", "medium", "case") for a in self.alerts]


READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1")


def _alert(name: str, *, nodes: list[str], edges: list[str] = (), events: list[str] = (),  # type: ignore[assignment]
           words: str | None = None, minute: int = 0) -> Alert:  # fmt: skip
    return Alert(id=name, rule_id="typology:r1", owner_id="deployer", mode=AlertMode.FULL,
                 referent_node_ids=nodes, edge_ids=list(edges), event_ids=list(events),
                 investigation_id=CASE, created_at=NOW.replace(minute=minute),
                 typology="structuring",
                 words=words or f"Finding {name} over n-a")  # fmt: skip


def _world(hidden: set[str], alerts: list[Alert]) -> tuple[Store, Graph, Analytics, Recorder]:
    recorder = Recorder()
    return Store(alerts), Graph(recorder, hidden), Analytics(recorder, hidden), recorder


async def _shown(store: Store, graph: Graph, analytics: Analytics) -> list[str]:
    queued = await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
    return [q.alert.id for q in queued]


V1 = _alert("v1", nodes=["n-a"], edges=["e-1"], events=["t-1"], minute=3)
V2 = _alert("v2", nodes=["n-b"], edges=["e-2"], events=["t-2"], minute=1)
OVER_LINK = _alert("h-link", nodes=["n-a", "n-b"], edges=["e-secret"], events=["t-3"], minute=2)
OVER_TRANSACTION = _alert(
    "h-txn", nodes=["n-a", "n-b"], edges=["e-1"], events=["t-secret"], minute=2
)


@pytest.mark.parametrize(
    ("hidden_alert", "hidden_id"), [(OVER_LINK, "e-secret"), (OVER_TRANSACTION, "t-secret")]
)
async def test_an_alert_over_hidden_evidence_is_withheld_whole(
    hidden_alert: Alert, hidden_id: str
) -> None:
    """Red with only nodes checked: its nodes are all readable, so the old queue listed it."""
    store, graph, analytics, _ = _world({hidden_id}, [V1, hidden_alert, V2])
    assert await _shown(store, graph, analytics) == ["v1", "v2"]


@pytest.mark.parametrize(
    ("hidden_alert", "hidden_id"), [(OVER_LINK, "e-secret"), (OVER_TRANSACTION, "t-secret")]
)
async def test_withholding_says_nothing_by_count_or_order(
    hidden_alert: Alert, hidden_id: str
) -> None:
    """The queue with the hidden alert, as the reader sees it, is the queue without it."""
    with_it = await _shown(*_world({hidden_id}, [V1, hidden_alert, V2])[:3])
    without_it = await _shown(*_world({hidden_id}, [V1, V2])[:3])
    assert with_it == without_it


@pytest.mark.parametrize(
    ("hidden_alert", "hidden_id"), [(OVER_LINK, "e-secret"), (OVER_TRANSACTION, "t-secret")]
)
async def test_the_reads_are_the_same_whether_the_evidence_is_hidden_or_not(
    hidden_alert: Alert, hidden_id: str
) -> None:
    """The same rows, once with the evidence hidden and once readable: the same calls with the same
    ids, one batched read per kind, so the work done does not depend on what is hidden."""
    store, graph, analytics, hidden_reads = _world({hidden_id}, [V1, hidden_alert, V2])
    await _shown(store, graph, analytics)
    store, graph, analytics, open_reads = _world(set(), [V1, hidden_alert, V2])
    assert await _shown(store, graph, analytics) == ["v1", hidden_alert.id, "v2"]
    assert hidden_reads.calls == open_reads.calls
    assert [c[0] for c in open_reads.calls] == ["get_nodes", "get_edges", f"list_events:{CASE}"]


async def test_transactions_are_asked_in_chunks_of_what_is_cited_not_of_what_is_found() -> None:
    """More cited transactions than one request may ask for: the requests are cut from the ids
    cited, so how many there are cannot follow how many the reader may see (a page boundary
    would)."""
    many = [f"t-{i:03d}" for i in range(450)]
    big = _alert("big", nodes=["n-a"], edges=["e-1"], events=many)
    store, graph, analytics, hidden_reads = _world({"t-007", "t-300"}, [big, V1])
    assert await _shown(store, graph, analytics) == ["v1"]
    store, graph, analytics, open_reads = _world(set(), [big, V1])
    assert await _shown(store, graph, analytics) == ["big", "v1"]
    assert hidden_reads.calls == open_reads.calls
    assert [c[1] for c in open_reads.calls if c[0].startswith("list_events")] == [200, 200, 51]


async def test_the_case_queue_inherits_the_check() -> None:
    """`queue` (the Reports figures, the reporting feed and neighbourhood risk count through it)."""
    store, graph, analytics, _ = _world({"t-secret"}, [V1, OVER_TRANSACTION, V2])
    queued = await alert_queue.queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
    assert [q.alert.id for q in queued] == ["v1", "v2"]


# ---- G3: the inbox -------------------------------------------------------------------------------

WORDED = _alert(
    "worded", nodes=["n-a", "n-b"], edges=["e-secret"], events=["t-1"],
    words="Structuring: A. Customer (account 40-11-22 12345678) paid B. Customer 9 times, "
    "each under 10,000",
)  # fmt: skip


@pytest.mark.parametrize("hidden_id", ["e-secret", "t-1", "n-b"])
async def test_the_inbox_withholds_a_worded_alert_s_words_with_its_evidence(hidden_id: str) -> None:
    """A worded typology alert, read through the inbox as a principal who may not see one of its
    link, transaction or node: no words and no referents. Red with the words returned as stored."""
    alert = WORDED.model_copy(
        update={"edge_ids": ["e-secret"] if hidden_id == "e-secret" else ["e-1"]}
    )
    _, graph, analytics, _ = _world({hidden_id}, [alert])
    view = await alert_to_view(alert, READER, graph, analytics)  # type: ignore[arg-type]
    assert view.evidence_available is False
    assert view.words is None
    assert view.referent_node_ids == []
    assert view.fired_on is None


async def test_the_inbox_shows_the_words_when_every_piece_of_evidence_is_readable() -> None:
    alert = WORDED.model_copy(update={"edge_ids": ["e-1"]})
    _, graph, analytics, _ = _world(set(), [alert])
    view = await alert_to_view(alert, READER, graph, analytics)  # type: ignore[arg-type]
    assert view.evidence_available is True
    assert view.words == WORDED.words


async def test_a_notify_stub_has_no_evidence_to_withhold() -> None:
    stub = Alert(
        id=new_id(), rule_id="hotlist:h1", owner_id="o", mode=AlertMode.NOTIFY_STUB, created_at=NOW
    )
    _, graph, analytics, recorder = _world(set(), [stub])
    view = await alert_to_view(stub, READER, graph, analytics)  # type: ignore[arg-type]
    assert view.evidence_available is True
    assert recorder.calls == []


# ---- the triage paths and the canvas: refused exactly as a missing alert ----------------------------


class TriageStore(Store):
    """`AlertStore.get_queue_alert` and its writes. An id not in the case is not found, as the real
    store answers; every write is recorded, so a refused action can be shown to have written nothing."""

    def __init__(self, alerts: list[Alert]) -> None:
        super().__init__(alerts)
        self.writes: list[str] = []

    async def get_queue_alert(self, alert_id: str, investigation_id: str, reader: Principal) -> QueueRow:
        from services.api.alerts import AlertNotFoundError

        for a in self.alerts:
            if a.id == alert_id and a.investigation_id == investigation_id:
                return QueueRow(a, "typology", "medium", "case")
        raise AlertNotFoundError(alert_id)

    async def set_queue_triage(self, alert_id: str, *_: Any, **__: Any) -> Alert:
        self.writes.append(f"triage {alert_id}")
        return next(a for a in self.alerts if a.id == alert_id)

    async def __getattr__(self, name: str) -> Any:  # any other write
        raise AssertionError(f"the store was asked to {name}")


def _path(name: str) -> Any:
    """Each path, called as its route calls it, on `alert_id`."""
    member = READER

    async def call(store: Any, graph: Any, analytics: Any, alert_id: str) -> Any:
        if name == "dispose":
            return await alert_queue.dispose(store, graph, analytics, CASE, alert_id, member,
                                             disposition="false_positive", reason="checked")  # fmt: skip
        if name == "assign":
            return await alert_queue.assign(store, graph, analytics, CASE, alert_id, member,
                                            assignee="someone", allowed={"someone"})  # fmt: skip
        function = getattr(alert_queue, name)
        return await function(store, graph, analytics, CASE, alert_id, member)

    return call


PATHS = ["claim", "release", "dispose", "approve_close", "send_back", "assign", "canvas_elements"]


@pytest.mark.parametrize("hidden", ["e-secret", "t-secret"])
@pytest.mark.parametrize("path", PATHS)
async def test_each_path_refuses_an_alert_over_hidden_evidence_as_missing(path: str, hidden: str) -> None:
    """Red with the nodes-only check: every node of the alert is readable, so the path went on (and a
    triage path wrote, and returned the alert's words; the canvas drew it without the hidden link)."""
    from services.api.alerts import AlertNotFoundError

    withheld = (OVER_LINK if hidden == "e-secret" else OVER_TRANSACTION).model_copy(
        update={"status": "closing" if path in ("approve_close", "send_back") else "claimed"
                if path == "release" else "open", "close_proposed_by": "other", "disposition":
                "false_positive", "assignee": READER.id if path == "release" else None}
    )  # fmt: skip
    call = _path(path)
    store, graph, analytics, _ = _world({hidden}, [withheld])
    triage = TriageStore([withheld])
    with pytest.raises(AlertNotFoundError) as refused:
        await call(triage, graph, analytics, withheld.id)
    missing_store = TriageStore([withheld])
    with pytest.raises(AlertNotFoundError) as missing:
        await call(missing_store, graph, analytics, "no-such-alert")
    assert type(refused.value) is type(missing.value)
    assert triage.writes == [] == missing_store.writes


@pytest.mark.parametrize("hidden", ["e-secret", "t-secret"])
async def test_the_canvas_answers_as_the_explanation_does(hidden: str) -> None:
    """The whole alert refused, never drawn in part: the canvas and the explanation both answer
    not found for it."""
    from services.api.alerts import AlertNotFoundError

    withheld = OVER_LINK if hidden == "e-secret" else OVER_TRANSACTION
    _, graph, analytics, _ = _world({hidden}, [withheld])
    store = TriageStore([withheld])
    answers = []
    for read in (alert_queue.canvas_elements, alert_queue.explain):
        try:
            await read(store, graph, analytics, CASE, withheld.id, READER)  # type: ignore[arg-type]
            answers.append("answered")
        except AlertNotFoundError:
            answers.append("not found")
    assert answers == ["not found", "not found"]


@pytest.mark.parametrize("hidden", ["e-secret", "t-secret"])
def test_a_claim_on_a_withheld_alert_writes_nothing_and_is_refused_as_for_a_missing_one(
    hidden: str,
) -> None:
    """At the route: the claim of an alert over hidden evidence and the claim of an id that never
    existed get the same answer, write nothing to the store and record the same in the audit
    (nothing: a refused claim is not a claim). Red with the nodes-only check, which claimed it and
    audited `alert_claimed` with its referents."""
    from fastapi.testclient import TestClient
    from services.api.app import (
        app,
        get_alerts_store,
        get_analytics,
        get_audit,
        get_graph,
        get_investigations,
        get_principal,
    )
    from services.api.investigations import AccessLevel

    from tests.services.api.test_monitoring_routes import _Case, _no_lifespan

    class Audit:
        def __init__(self) -> None:
            self.records: list[str] = []

        async def record(self, **kwargs: Any) -> None:
            self.records.append(str(kwargs.get("action")))

    triager = READER.model_copy(update={"roles": ["analyst"]})
    withheld = OVER_LINK if hidden == "e-secret" else OVER_TRANSACTION
    _, graph, analytics, _ = _world({hidden}, [withheld])
    store, audit = TriageStore([withheld]), Audit()
    previous = app.router.lifespan_context
    app.router.lifespan_context = _no_lifespan
    app.dependency_overrides.update({
        get_principal: lambda: triager,
        get_investigations: lambda: _Case(CASE, {triager.id: AccessLevel.EDITOR}),
        get_graph: lambda: graph,
        get_analytics: lambda: analytics,
        get_alerts_store: lambda: store,
        get_audit: lambda: audit,
    })  # fmt: skip
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            answers = []
            for alert_id in (withheld.id, "no-such-alert"):
                response = client.post(f"/v1/investigations/{CASE}/alert-queue/{alert_id}/claim")
                answers.append((response.status_code, response.json(), list(audit.records)))
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = previous
    assert answers[0] == answers[1] == (404, {"error": "alert_not_found"}, [])
    assert store.writes == []
