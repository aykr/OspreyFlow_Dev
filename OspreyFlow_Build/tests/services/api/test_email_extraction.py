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
    NotDocumentsError,
    email_document_id,
)
from services.api.link_notes import LinkNotFoundError
from services.api.review import ExtractionCandidateNotFoundError
from services.api.review import (
    CandidateNotPendingError,
    CandidateStatus,
    DocumentNotFoundError,
    ExtractionCandidate,
    ExtractionCandidateRecord,
)
from services.api.working_set.models import DeltaAdd, LimitExceededError
from services.api.working_set.service import WorkingSetService

from ontology.loader import load_default_ontology
from ontology.validation import validate_properties
from schemas.analytics import EventListRequest, EventListResult, EventRecord
from schemas.domain import (
    AuditStub,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    Handling,
    Interval,
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
            and (f.window is None or e.occurred_at >= f.window.valid_from)
            and (
                f.window is None
                or f.window.valid_to is None
                or e.occurred_at <= f.window.valid_to
            )
        ]
        # Newest first and paged, as the adapter's `list_events` is.
        matching.sort(key=lambda e: e.occurred_at, reverse=True)
        return EventListResult(
            total=len(matching), events=matching[req.offset : req.offset + req.limit]
        )


class WritingGraph(FakeGraphPort):
    """Keeps every node and link it is given, and hands a written node back by id. Refuses what the
    ArcadeDB adapter refuses (rule 15): every write is checked against the ontology with the same
    `validate_properties` the adapter calls, so a Document carrying a property the ontology does
    not declare fails here as it fails there (the defect the owner saw on 4 October 2026)."""

    def __init__(self) -> None:
        super().__init__(Subgraph(nodes=[], edges=[]), candidate_count=0)
        self.nodes: dict[str, NodeWrite] = {}
        self._pending_nodes: dict[TxId, list[NodeWrite]] = {}

    async def begin_transaction(self) -> TxId:
        tx = await super().begin_transaction()
        self._pending_nodes[tx] = []
        return tx

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]:
        for n in nodes:
            entity_type = ONTOLOGY.entity_type(n.type)
            assert entity_type is not None, n.type
            validate_properties(entity_type, n.properties)
        self._pending_nodes[tx].extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]:
        for e in edges:
            edge_type = ONTOLOGY.edge_type(e.type)
            assert edge_type is not None, e.type
            validate_properties(edge_type, e.properties)
        return await super().upsert_edges(edges, tx)

    async def commit_transaction(self, tx: TxId) -> None:
        for n in self._pending_nodes.pop(tx, []):
            self.nodes[n.id] = n
        await super().commit_transaction(tx)

    async def rollback_transaction(self, tx: TxId) -> None:
        self._pending_nodes.pop(tx, None)
        await super().rollback_transaction(tx)

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        """The written nodes asked for, as the real adapter returns the requested nodes it can
        show (rule 15): answering nothing hid the reader's marks for an entity marked by hand."""
        nodes = [n for n in [await self.get_node(i, principal) for i in req.node_ids] if n]
        return Subgraph(nodes=nodes, edges=[])

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

    async def get_document_text(self, document_id: str, principal: Principal) -> str:
        found = self.texts.get(document_id)
        if found is None or found[1] != principal.org_unit:
            raise DocumentNotFoundError(document_id)
        return found[0]

    async def list_for_document(
        self, document_id: str, principal: Principal
    ) -> list[ExtractionCandidateRecord]:
        return [
            r
            for r in self.records.values()
            if r.document_id == document_id and r.owning_unit == principal.org_unit
        ]

    async def get_authorized(
        self, candidate_id: str, principal: Principal
    ) -> ExtractionCandidateRecord:
        record = self.records.get(candidate_id)
        if record is None or record.owning_unit != principal.org_unit:
            # As the real store refuses (rule 15): not found, whether absent or another unit's.
            raise ExtractionCandidateNotFoundError(candidate_id)
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


# --- rejecting a finding (owner, 6 October 2026: "allow for a reject button too") --------------


async def test_rejecting_marks_the_finding_rejected_and_writes_nothing() -> None:
    service, graph, _, candidates, _ = await _build()
    extracted = await service.extract("inv-1", "e1", "ev-1", ANALYST)
    before_nodes, before_edges = dict(graph.nodes), list(graph.committed_edges)
    await service.reject("inv-1", "e1", "ev-1", extracted.candidates[0].id, ANALYST)
    assert candidates.records[extracted.candidates[0].id].status is CandidateStatus.REJECTED
    assert graph.nodes == before_nodes and graph.committed_edges == before_edges


async def test_a_finding_from_another_email_cannot_be_rejected_through_this_one() -> None:
    service, _, _, candidates, _ = await _build([_event("ev-1"), _event("ev-2")])
    first = await service.extract("inv-1", "e1", "ev-1", ANALYST)
    with pytest.raises(EmailNotFoundError):
        await service.reject("inv-1", "e1", "ev-2", first.candidates[0].id, ANALYST)
    assert candidates.records[first.candidates[0].id].status is CandidateStatus.PENDING


async def test_an_analyst_of_another_unit_cannot_reject_a_finding_they_cannot_see() -> None:
    """Rule 4: the link is the other unit's, so they are refused as if it did not exist, and the
    finding is left as it was."""
    service, _, _, candidates, _ = await _build()
    extracted = await service.extract("inv-1", "e1", "ev-1", ANALYST)
    with pytest.raises((LinkNotFoundError, EmailNotFoundError, ExtractionCandidateNotFoundError)):
        await service.reject("inv-1", "e1", "ev-1", extracted.candidates[0].id, OTHER_UNIT)
    assert candidates.records[extracted.candidates[0].id].status is CandidateStatus.PENDING


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


# --- the emails behind a link onto the canvas as Documents (ADR-092) --------------------------


def _at(event_id: str, day: int) -> EventRecord:
    sent = datetime(2001, 5, day, 10, tzinfo=UTC)
    return _event(event_id).model_copy(update={"occurred_at": sent})


async def test_the_emails_in_the_window_are_written_as_documents_and_drawn() -> None:
    events = [_at("ev-1", 1), _at("ev-2", 10), _at("ev-3", 20)]
    service, graph, working, _, _ = await _build(events)
    window = Interval(
        valid_from=datetime(2001, 5, 5, tzinfo=UTC), valid_to=datetime(2001, 5, 25, tzinfo=UTC)
    )
    result = await service.show_as_documents("inv-1", "e1", ANALYST, window=window)
    written = {email_document_id("ev-2"), email_document_id("ev-3")}
    assert set(graph.nodes) == written
    assert result.written == 2
    assert {n.id for n in result.delta.nodes} == written
    for doc in written:
        assert await working.get_node("inv-1", doc) is not None
    # Each email is linked to both addresses, as extraction links it.
    ends = sorted((e.source, e.target) for e in graph.committed_edges)
    assert ends == sorted([("a", d) for d in written] + [("b", d) for d in written])


async def test_with_nothing_brushed_every_email_on_the_link_is_written() -> None:
    events = [_at(f"ev-{n}", n) for n in range(1, 8)] + [_event("ev-off", "other")]
    service, graph, _, _, _ = await _build(events)
    result = await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert result.written == 7
    assert email_document_id("ev-off") not in graph.nodes


async def test_showing_the_same_emails_twice_adds_nothing_new() -> None:
    service, graph, working, _, _ = await _build([_at("ev-1", 1), _at("ev-2", 2)])
    await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    before = len(await working.node_ids("inv-1"))
    again = await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert len(await working.node_ids("inv-1")) == before
    assert again.written == 2  # the same derived ids, upserted, not duplicated
    assert len(graph.nodes) == 2


async def test_past_the_cap_nothing_is_written_and_the_answer_is_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.api.working_set.service as service_module

    service, graph, working, _, _ = await _build([_at(f"ev-{n}", n) for n in range(1, 6)])
    existing = len(await working.node_ids("inv-1"))
    monkeypatch.setattr(service_module, "MAX_NODES", existing + 2)
    with pytest.raises(LimitExceededError) as refused:
        await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert refused.value.detail.would_be == existing + 5
    assert graph.nodes == {} and graph.committed_edges == []
    assert len(await working.node_ids("inv-1")) == existing


@pytest.mark.parametrize("edge_id", ["secret-link", "secret-end", "no-such-link"])
async def test_documents_for_a_hidden_or_missing_link_refuse_alike_and_write_nothing(
    edge_id: str,
) -> None:
    service, graph, _, _, _ = await _build([_event("ev-1", "secret-link")])
    with pytest.raises(LinkNotFoundError):
        await service.show_as_documents("inv-1", edge_id, ANALYST, window=None)
    assert graph.nodes == {}


async def test_extraction_past_the_cap_writes_nothing_to_the_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before ADR-092 the graph was written first and the cap checked after, so a full working
    set kept a Document the canvas refused: rule 2's "rejected whole" broken."""
    import services.api.working_set.service as service_module

    service, graph, working, _, _ = await _build()
    monkeypatch.setattr(service_module, "MAX_NODES", len(await working.node_ids("inv-1")))
    with pytest.raises(LimitExceededError):
        await service.extract("inv-1", "e1", "ev-1", ANALYST)
    assert graph.nodes == {} and graph.committed_edges == []


def _transaction(event_id: str) -> EventRecord:
    """The shape a PaySim event has: an amount on the link, no text."""
    return _event(event_id).model_copy(update={"properties": {"amount": 181.0, "kind": "TRANSFER"}})


async def test_a_link_whose_events_have_no_text_is_refused_and_writes_nothing() -> None:
    """ADR-092 Amendment 1: a PaySim transaction or an HMP incident is an event, not a document;
    writing it as a "(no subject)" Document would put empty pages on the canvas."""
    service, graph, _, _, _ = await _build([_transaction("tx-1"), _transaction("tx-2")])
    with pytest.raises(NotDocumentsError):
        await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert graph.nodes == {}


async def test_events_without_text_are_counted_not_written() -> None:
    service, graph, _, _, _ = await _build([_at("ev-1", 1), _transaction("tx-1")])
    result = await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert (result.written, result.without_text) == (1, 1)
    assert set(graph.nodes) == {email_document_id("ev-1")}


async def test_an_email_without_a_message_id_is_written_without_one() -> None:
    """A missing id is left out, not written as null, which the ontology's `string` refuses."""
    bare = _event("ev-1").model_copy(update={"properties": {"subject": "Hi", "excerpt": TEXT}})
    service, graph, _, _, _ = await _build([bare])
    await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert "message_id" not in graph.nodes[email_document_id("ev-1")].properties


async def test_a_message_with_no_subject_is_titled_by_its_first_words() -> None:
    """ADR-094: an SMS has no subject; its Document is named by what it says, not "(no subject)"."""
    sms = _event("ev-1").model_copy(
        update={
            "properties": {
                "excerpt": "Callum, the van is booked for Friday. "
                "Pick it up from Unit 4, Marsh Lane."
            }
        }
    )
    service, graph, _, _, _ = await _build([sms])
    await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    title = graph.nodes[email_document_id("ev-1")].properties["title"]
    assert title.startswith("Callum, the van is booked for Friday.")
    assert len(title) <= 60
