"""Entities from an email behind a link — `06_DECISIONS.md` ADR-089 step 3. The service's own
rules against `FakeWorkingSetStore`, a graph stand-in that keeps what it is given, an analytics
stand-in that answers the filter it is given, a candidate store stand-in scoped by owning unit as
the real one is, and a model stand-in with fixed findings.

The sentences under test:

* The email becomes a `Document` node at the first extraction, linked to sender and recipient by
  `MENTIONED_IN`, and both are put into the working set; the text and the pending candidates are
  kept under `email:<event id>`, and nothing a model found reaches the graph until accepted.
* Accepting a candidate writes it as an `inferred` node *and* a `MENTIONED_IN` link to the email's
  Document, and puts both into the working set.
* Only someone who can see the link may do either; a hidden link and a missing one refuse
  identically and write nothing; an event not on the link, or a candidate not from the email, is
  not found.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.email_extraction import (
    EmailExtractionService,
    EmailNotFoundError,
    email_document_id,
)
from services.api.link_notes import LinkNotFoundError
from services.api.review import (
    CandidateNotPendingError,
    CandidateStatus,
    ExtractionCandidate,
    ExtractionCandidateRecord,
)
from services.api.working_set.models import DeltaAdd
from services.api.working_set.service import WorkingSetService

from ontology.loader import load_default_ontology
from schemas.analytics import EventListRequest, EventListResult, EventRecord
from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    NodeId,
    NodeWrite,
    Principal,
    ProvenanceState,
    Subgraph,
    TxId,
)
from schemas.model import ExtractionRequest, ExtractionResult

from .test_link_events import _Cases, _in_scope
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

ONTOLOGY = load_default_ontology()
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
OTHER_UNIT = Principal(id="analyst-9", clearance="OFFICIAL", org_unit="unit-9")
HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
TEXT = "Dana MERCER wrote to Callum PRICE about the Dabhol plant."


def _event(event_id: str, edge_id: str = "e1") -> EventRecord:
    return EventRecord(
        event_id=event_id,
        edge_id=edge_id,
        edge_type="COMMUNICATED_WITH",
        source_id="a",
        target_id="b",
        occurred_at=datetime(2001, 5, 14, 10, tzinfo=UTC),
        direction="outbound",
        properties={"subject": "Dabhol", "excerpt": TEXT, "message_id": "<1@thyme>"},
        investigation_scope="inv-1",
        handling=HANDLING,
    )


#: The DuckDB adapter's `_TOP_LEVEL_FIELDS`: any other `value_filters` name is read from
#: `properties`. Restated so this stand-in refuses what the real store refuses (rule 15): a
#: `value_filters` entry on `event_id` matches nothing, which hid ADR-089 step 3's defect.
_TOP_LEVEL = {"edge_type", "source_id", "target_id", "cell_site", "direction"}


def _field(e: EventRecord, name: str) -> object:
    return getattr(e, name) if name in _TOP_LEVEL else e.properties.get(name)


class RecordingAnalytics:
    def __init__(self, events: list[EventRecord]) -> None:
        self.events = events

    async def list_events(self, req: EventListRequest, principal: Principal) -> EventListResult:
        f = req.filter
        matching = [
            e
            for e in self.events
            if _in_scope(e, f)
            and (not f.edge_ids or e.edge_id in f.edge_ids)
            and (not f.event_ids or e.event_id in f.event_ids)
            and all(_field(e, name) in values for name, values in f.value_filters.items() if values)
        ]
        return EventListResult(total=len(matching), events=matching[: req.limit])


class WritingGraph(FakeGraphPort):
    """Keeps every node and link it is given, and hands a written node back by id."""

    def __init__(self) -> None:
        super().__init__(Subgraph(nodes=[], edges=[]), candidate_count=0)
        self.nodes: dict[str, NodeWrite] = {}
        self._pending_nodes: dict[TxId, list[NodeWrite]] = {}

    async def begin_transaction(self) -> TxId:
        tx = await super().begin_transaction()
        self._pending_nodes[tx] = []
        return tx

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]:
        self._pending_nodes[tx].extend(nodes)
        return [n.id for n in nodes]

    async def commit_transaction(self, tx: TxId) -> None:
        for n in self._pending_nodes.pop(tx, []):
            self.nodes[n.id] = n
        await super().commit_transaction(tx)

    async def rollback_transaction(self, tx: TxId) -> None:
        self._pending_nodes.pop(tx, None)
        await super().rollback_transaction(tx)

    async def get_node(self, node_id: NodeId, principal: Principal, **_: Any) -> Node | None:
        w = self.nodes.get(node_id)
        if w is None:
            return None
        return Node(
            id=w.id,
            type=w.type,
            properties=w.properties,
            provenance=w.provenance,
            handling=w.handling,
            audit=AuditStub(created_at=w.created_at, created_by=w.created_by),
        )


class InMemoryCandidates:
    """Refuses what the Postgres store refuses: a candidate or a text is read only by its owning
    unit, and a candidate is reviewed once."""

    def __init__(self) -> None:
        self.records: dict[str, ExtractionCandidateRecord] = {}
        self.texts: dict[str, tuple[str, str]] = {}

    async def store(
        self, candidates: Sequence[ExtractionCandidate], principal: Principal
    ) -> list[ExtractionCandidateRecord]:
        out = []
        for c in candidates:
            record = ExtractionCandidateRecord(
                **c.model_dump(),
                status=CandidateStatus.PENDING,
                owning_unit=principal.org_unit,
                created_by=principal.id,
                created_at=datetime.now(UTC),
            )
            self.records[record.id] = record
            out.append(record)
        return out

    async def store_document_text(self, document_id: str, text: str, principal: Principal) -> None:
        self.texts[document_id] = (text, principal.org_unit)

    async def get_authorized(
        self, candidate_id: str, principal: Principal
    ) -> ExtractionCandidateRecord:
        record = self.records.get(candidate_id)
        if record is None or record.owning_unit != principal.org_unit:
            raise KeyError(candidate_id)
        return record

    async def mark_reviewed(
        self,
        candidate_id: str,
        principal: Principal,
        *,
        status: CandidateStatus,
        node_id: str | None = None,
    ) -> None:
        record = await self.get_authorized(candidate_id, principal)
        if record.status is not CandidateStatus.PENDING:
            raise CandidateNotPendingError(candidate_id)
        self.records[candidate_id] = record.model_copy(
            update={"status": status, "node_id": node_id, "reviewed_by": principal.id}
        )


class FixedModel:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data
        self.requests: list[ExtractionRequest] = []

    async def extract(self, req: ExtractionRequest) -> ExtractionResult:
        self.requests.append(req)
        return ExtractionResult(document_id=req.document_id, model=req.model, data=self.data)


async def _build(
    events: list[EventRecord] | None = None, investigations: object | None = None
) -> tuple[
    EmailExtractionService, WritingGraph, FakeWorkingSetStore, InMemoryCandidates, FixedModel
]:
    working = FakeWorkingSetStore()
    await working.add_nodes("inv-1", [node("a"), node("b"), node("c", "SECRET")])
    await working.add_edges(
        "inv-1",
        [
            edge("e1", "a", "b"),
            edge("secret-link", "a", "b", "SECRET"),
            edge("secret-end", "a", "c"),
        ],
    )
    graph = WritingGraph()
    candidates = InMemoryCandidates()
    model = FixedModel(
        {"Person": [{"family_name": "MERCER", "given_names": "Dana", "confidence": 0.9}]}
    )
    analytics = RecordingAnalytics(
        events if events is not None else [_event("ev-1"), _event("ev-9", "other")]
    )
    service = EmailExtractionService(
        WorkingSetService(graph, working, SCHEME),
        analytics,  # type: ignore[arg-type]
        graph,
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        model,  # type: ignore[arg-type]
        "local-model",
        investigations=investigations,  # type: ignore[arg-type]
    )
    await working.add_nodes("branch-1", [node("a"), node("b")])
    await working.add_edges("branch-1", [edge("e1", "a", "b")])
    return service, graph, working, candidates, model


async def test_extracting_writes_the_email_as_a_document_and_keeps_candidates_pending() -> None:
    service, graph, working, candidates, model = await _build()
    result = await service.extract("inv-1", "e1", "ev-1", ANALYST)

    document_id = email_document_id("ev-1")
    assert result.document_id == document_id
    written = graph.nodes[document_id]
    assert written.type == "Document"
    assert written.properties["title"] == "Dabhol"
    assert written.handling == HANDLING
    mentions = [e for e in graph.committed_edges if e.type == "MENTIONED_IN"]
    assert sorted((e.source, e.target) for e in mentions) == [
        ("a", document_id),
        ("b", document_id),
    ]
    # Into the working set, in one delta, so the canvas shows them at once.
    assert isinstance(result.delta, DeltaAdd)
    assert [n.id for n in result.delta.nodes] == [document_id]
    assert len(result.delta.edges) == 2
    assert await working.get_node("inv-1", document_id) is not None
    # The text and the candidates are kept under the email's document id; nothing of the model's
    # reached the graph.
    assert candidates.texts[document_id] == (TEXT, "unit-1")
    assert [c.status for c in result.candidates] == [CandidateStatus.PENDING]
    assert result.candidates[0].document_id == document_id
    assert all(w.type == "Document" for w in graph.nodes.values())
    # The model saw the email's text, under the deployment's local model when none was named.
    assert model.requests[0].text == TEXT
    assert model.requests[0].model == "local-model"


async def test_the_callers_model_is_used_when_named() -> None:
    service, _, _, _, model = await _build()
    await service.extract("inv-1", "e1", "ev-1", ANALYST, model="bigger-model")
    assert model.requests[0].model == "bigger-model"


async def test_accepting_writes_an_inferred_node_linked_to_the_email_into_the_working_set() -> None:
    service, graph, working, candidates, _ = await _build()
    extracted = await service.extract("inv-1", "e1", "ev-1", ANALYST)
    candidate = extracted.candidates[0]

    accepted = await service.accept("inv-1", "e1", "ev-1", candidate.id, ANALYST)
    person = graph.nodes[accepted.node_id]
    assert person.type == "Person"
    assert person.provenance.state is ProvenanceState.INFERRED
    mention = [e for e in graph.committed_edges if e.source == accepted.node_id]
    assert [(e.type, e.target) for e in mention] == [("MENTIONED_IN", email_document_id("ev-1"))]
    assert mention[0].provenance.state is ProvenanceState.INFERRED
    assert [n.id for n in accepted.delta.nodes] == [accepted.node_id]
    assert len(accepted.delta.edges) == 1
    assert await working.get_node("inv-1", accepted.node_id) is not None
    assert candidates.records[candidate.id].status is CandidateStatus.ACCEPTED


@pytest.mark.parametrize("edge_id", ["secret-link", "secret-end", "no-such-link"])
async def test_a_hidden_link_and_a_missing_link_refuse_identically_and_write_nothing(
    edge_id: str,
) -> None:
    service, graph, _, candidates, model = await _build()
    with pytest.raises(LinkNotFoundError) as refused:
        await service.extract("inv-1", edge_id, "ev-1", ANALYST)
    assert str(refused.value) == str(LinkNotFoundError(edge_id))
    assert graph.nodes == {} and graph.committed_edges == []
    assert candidates.records == {} and model.requests == []


async def test_an_event_that_is_not_on_the_link_is_not_found_and_writes_nothing() -> None:
    service, graph, _, _, model = await _build()
    with pytest.raises(EmailNotFoundError):
        await service.extract("inv-1", "e1", "ev-9", ANALYST)  # ev-9 is on another link
    with pytest.raises(EmailNotFoundError):
        await service.extract("inv-1", "e1", "no-such-event", ANALYST)
    assert graph.nodes == {} and model.requests == []


async def test_a_candidate_from_another_email_cannot_be_accepted_through_this_one() -> None:
    service, graph, _, _, _ = await _build([_event("ev-1"), _event("ev-2")])
    first = await service.extract("inv-1", "e1", "ev-1", ANALYST)
    await service.extract("inv-1", "e1", "ev-2", ANALYST)
    before = len(graph.committed_edges)
    with pytest.raises(EmailNotFoundError):
        await service.accept("inv-1", "e1", "ev-2", first.candidates[0].id, ANALYST)
    assert len(graph.committed_edges) == before


async def test_an_email_loaded_under_the_original_case_can_be_extracted_from_a_branch() -> None:
    """ADR-084 Amendment 2: the emails behind a branch's link were loaded under the case it came
    from; extracting from one on the branch finds it there, and the Document joins the branch."""
    service, graph, working, _, _ = await _build(investigations=_Cases({"inv-1", "branch-1"}))
    result = await service.extract("branch-1", "e1", "ev-1", ANALYST)
    assert result.document_id == email_document_id("ev-1")
    assert await working.get_node("branch-1", result.document_id) is not None


async def test_a_branch_cannot_extract_an_email_from_a_parent_the_analyst_cannot_see() -> None:
    service, _, _, _, _ = await _build(investigations=_Cases({"branch-1"}))
    with pytest.raises(EmailNotFoundError):
        await service.extract("branch-1", "e1", "ev-1", ANALYST)
