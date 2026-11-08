"""A case made from another before L3.2 writes nothing until the upgrade converts it (L3.2 item 3,
from L3.1's final review; the lane review's round 2; ADR-144 Amendment 1).

Such a case reads its original's dataset and, for a reader holding a level on the original, the
original's layer. A write there naming no dataset (an accepted proposal, an extraction, a rule's
`ALERTED_ON`) would land in the source the original reads. A merge into a node the writer cannot
read would carry the original's work into it, since the adapter unions a merged node's datasets.
So every write there is refused, for every reader, in one set of words, before anything is written
(`refuse_writing_in_an_unconverted_case`). The answer then says nothing about the layer (rule 3).

What a mistake here would do, and the case that catches it:

- a link, a new node or a merge written there, by a reader holding a level on the original or not:
  `test_every_unnamed_write_is_refused_alike_for_every_reader`;
- an accept path writing its node before the link is refused (an orphan in the source):
  `test_an_accept_writes_nothing_at_all`, with the early check alone removed in
  `test_the_early_check_refuses_before_the_candidate_is_read`;
- the refusal removed: `test_each_write_lands_with_the_refusal_removed`. Red at the real
  adapter's merge, a node of the original's layer carried into the source, in
  `test_unconverted_case_merge_live.py`.
"""


from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api import questions as questions_module
from services.api.dataset_scope import (
    scope_to_case,
    set_case_datasets,
    stamping,
)
from services.api.datasets import Dataset, InMemoryDatasetStore, TouchesTheOriginalsWorkError
from services.api.document_reader import DocumentReaderService
from services.api.email_extraction import EmailExtractionService, email_document_id
from services.api.questions import InMemoryQuestionStore, QuestionsService
from services.api.working_set.service import WorkingSetService

from conduit_common.identity import new_edge_id
from schemas.domain import (
    AuditStub,
    EdgeWrite,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .test_case_writes import HANDLING, _document
from .test_email_extraction import (
    ANALYST,
    ONTOLOGY,
    FakeRecogniser,
    FixedModel,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
)
from .test_questions import ANSWER
from .test_questions_graph_facts import TrendAnalytics
from .unconverted import made_before_l3_2
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

UNIT = ANALYST.org_unit


_in_this_case = _event("ev-1").model_copy(update={"investigation_scope": "made"})


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


async def _holds(principal: Principal, investigation_id: str) -> bool:
    return True  # the analyst holds a level on the original, so reads its layer


async def _nobody_holds(principal: Principal, investigation_id: str) -> bool:
    return False  # a member of the made case alone, holding no level on the original


async def _a_case_made_from_another(
    holds: Any = _holds,
) -> tuple[InMemoryDatasetStore, str, Principal]:
    """The original reads `src` and has its layer; `made` was made from it before L3.2 and is
    scoped as a request under it is. Returns the store, the original's layer and the principal."""
    store = InMemoryDatasetStore()
    store.add(
        Dataset(
            id="src",
            name="src",
            owning_unit=UNIT,
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
            created_by="seed",
        )
    )
    await store.set_for_case("original", ["src"], ANALYST, case_name="Original")
    layer = await made_before_l3_2(store, "original", "made")
    assert layer is not None
    principal = await scope_to_case(ANALYST, "made", store, holds_a_level=holds)
    assert (layer in (principal.datasets or [])) == (holds is _holds)
    return store, layer, principal


class _ReadsBack(WritingGraph):
    """`WritingGraph`, reading back what it committed as the adapter does: a node written and
    committed is then found by `get_nodes`, judged by its body for the reader."""

    def _world_nodes(self) -> dict[str, Node]:
        committed = {
            w.id: Node(
                id=w.id, type=w.type, properties=w.properties, provenance=w.provenance,
                handling=w.handling, datasets=w.datasets,
                audit=AuditStub(created_at=w.created_at, created_by=w.created_by),
            )  # fmt: skip
            for w in self.nodes.values()
        }
        return {**committed, **super()._world_nodes()}


def _held(graph: WritingGraph, *nodes: Node) -> WritingGraph:
    graph._graph_nodes.update({n.id: n for n in nodes})  # what `get_nodes` can find, by body
    return graph


async def _accept_a_proposal(document_in: str, holds: Any = _holds) -> tuple[WritingGraph, Any]:
    """Through the real `QuestionsService.ask` and `accept`: the proposal's `MENTIONED_IN` names no
    dataset and targets its Document, here kept in `document_in` (the original's layer or the
    source). Returns the graph and the outcome (or the error raised)."""
    store, layer, principal = await _a_case_made_from_another(holds)
    where = {"layer": [layer], "source": ["src"], "both": ["src", layer]}[document_in]
    doc = _document(email_document_id("ev-1")).model_copy(update={"datasets": where})
    working = FakeWorkingSetStore()
    pair = [node(n).model_copy(update={"datasets": ["src"]}) for n in ("a", "b")]
    await working.add_nodes("made", [*pair, doc])
    await working.add_edges("made", [edge("e1", "a", "b").model_copy(update={"datasets": ["src"]})])
    inner = _held(_ReadsBack(), doc, *pair)  # the pair is in the graph, as the case's are
    graph = stamping(inner, registry=store)
    candidates = InMemoryCandidates()
    working_set = WorkingSetService(graph, working, SCHEME)
    service = QuestionsService(
        working_set,
        DocumentReaderService(
            working_set,
            RecordingAnalytics([_in_this_case]),  # type: ignore[arg-type]
            graph,
            candidates,  # type: ignore[arg-type]
        ),
        graph,
        FixedModel(ANSWER),  # type: ignore[arg-type]
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        InMemoryQuestionStore(),
        default_model="local-model",
        analytics=TrendAnalytics([]),  # type: ignore[arg-type]
        datasets=store,
        investigations=None,
    )
    answered = await service.ask("made", "Who?", principal)
    person = next(c for c in answered.candidates if c.entity_type == "Person")
    try:
        return inner, await service.accept("made", person.id, principal)
    except TouchesTheOriginalsWorkError as refused:
        return inner, refused


async def _accept_from_an_email(document_in: str) -> tuple[WritingGraph, Any]:
    """Through the real `EmailExtractionService.extract` and `accept`: the node and its
    `MENTIONED_IN` to the email's Document, here kept in `document_in`."""
    store, layer, principal = await _a_case_made_from_another()
    where = layer if document_in == "layer" else "src"
    doc = _document(email_document_id("ev-1")).model_copy(update={"datasets": [where]})
    working = FakeWorkingSetStore()
    pair = [node(n).model_copy(update={"datasets": ["src"]}) for n in ("a", "b")]
    await working.add_nodes("made", pair)
    await working.add_edges("made", [edge("e1", "a", "b").model_copy(update={"datasets": ["src"]})])
    inner = _held(_ReadsBack(), doc, *pair)  # the pair is in the graph, as the case's are
    graph = stamping(inner, registry=store)
    service = EmailExtractionService(
        WorkingSetService(graph, working, SCHEME),
        RecordingAnalytics([_in_this_case]),  # type: ignore[arg-type]
        graph,
        ONTOLOGY,
        InMemoryCandidates(),  # type: ignore[arg-type]
        FixedModel(
            {"Person": [{"family_name": "MERCER", "given_names": "Dana", "confidence": 0.9}]}
        ),  # type: ignore[arg-type]
        "local-model",
        recogniser=FakeRecogniser(),
    )
    try:
        # The extraction writes the email's Document itself, so in the layer it is refused there,
        # merging into the layer's node; the acceptance's link would be refused next.
        extracted = await service.extract("made", "e1", "ev-1", principal)
        return inner, await service.accept(
            "made", "e1", "ev-1", extracted.candidates[0].id, principal
        )
    except TouchesTheOriginalsWorkError as refused:
        return inner, refused


def _mention_of(inner: WritingGraph, accepted: Any) -> EdgeWrite:
    """The accepted node's own `MENTIONED_IN` to its Document."""
    (mention,) = [e for e in inner.committed_edges if e.source == accepted.node_id]
    return mention


def _alerted_on(target: str) -> EdgeWrite:
    """As `rule_evaluation.write_alert_node` writes it: an `ALERTED_ON` naming no dataset, so the
    stamping graph gives it the case's first."""
    return EdgeWrite(
        id=new_edge_id(),
        type="ALERTED_ON",
        source="alert-1",
        target=target,
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id="rule:r-1", locator="alert", excerpt_hash="")],
            extracted_by="rule:r-1",
            first_seen=datetime(2026, 11, 8, tzinfo=UTC),
        ),
        handling=HANDLING,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
        created_by="rule:r-1",
    )


async def _write_link(to: str, holds: Any = _holds) -> tuple[WritingGraph, Exception | None]:
    store, layer, _ = await _a_case_made_from_another(holds)
    inner = _held(
        WritingGraph(),
        node("theirs").model_copy(update={"datasets": [layer]}),
        node("loaded").model_copy(update={"datasets": ["src"]}),
    )
    graph = stamping(inner, registry=store)
    tx = await graph.begin_transaction()
    try:
        # As `write_alert_node` does: the alert's own node first, in the same transaction.
        await graph.upsert_nodes([_merging("alert-1")], tx)
        await graph.upsert_edges([_alerted_on(to)], tx)
    except TouchesTheOriginalsWorkError as refused:
        await graph.rollback_transaction(tx)
        return inner, refused
    await graph.commit_transaction(tx)
    return inner, None


def _merging(node_id: str) -> NodeWrite:
    held = node(node_id)
    return NodeWrite(
        id=node_id,
        type=held.type,
        properties={"family_name": "MERCER", "given_names": "Dana"},
        provenance=held.provenance,
        handling=held.handling,
        created_at=datetime(2026, 11, 8, tzinfo=UTC),
        created_by="analyst-1",
    )


async def _write_node(node_id: str, holds: Any = _holds) -> tuple[WritingGraph, Exception | None]:
    store, layer, _ = await _a_case_made_from_another(holds)
    inner = _held(_ReadsBack(), node("theirs").model_copy(update={"datasets": [layer]}))
    graph = stamping(inner, registry=store)
    tx = await graph.begin_transaction()
    try:
        await graph.upsert_nodes([_merging(node_id)], tx)
    except TouchesTheOriginalsWorkError as refused:
        await graph.rollback_transaction(tx)
        return inner, refused
    await graph.commit_transaction(tx)
    return inner, None


READERS = pytest.mark.parametrize(
    "holds", [_holds, _nobody_holds], ids=["holds-a-level", "stranger"]
)


@READERS
async def test_every_unnamed_write_is_refused_alike_for_every_reader(holds: Any) -> None:
    """A link to a loaded node, a link to the original's node, a new node, and a merge into the
    original's node: each refused in the same words, nothing committed, whether or not the writer
    reads the original's layer."""
    outcomes = [
        await _write_link("loaded", holds),
        await _write_link("theirs", holds),
        await _write_node("new-one", holds),
        await _write_node("theirs", holds),
    ]
    words = set()
    for inner, refused in outcomes:
        assert isinstance(refused, TouchesTheOriginalsWorkError)
        assert inner.committed_edges == [] and inner.nodes == {}
        words.add(str(refused))
    assert len(words) == 1 and "waiting to become a view" in words.pop()


@pytest.mark.parametrize(
    "accept", [_accept_a_proposal, _accept_from_an_email], ids=["question", "email"]
)
@pytest.mark.parametrize("document_in", ["source", "layer"])
async def test_an_accept_writes_nothing_at_all(accept: Any, document_in: str) -> None:
    inner, outcome = await accept(document_in)
    assert isinstance(outcome, TouchesTheOriginalsWorkError)
    assert inner.committed_edges == []
    assert not [n for n in inner.nodes.values() if n.type == "Person"]


async def test_each_write_lands_with_the_refusal_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15, red: the refusal removed (the stamping graph's last word and the helper the accept
    paths ask first), a stranger's merge into the original's node is written into the source, and
    a link to the original's node lands too."""
    from services.api import dataset_scope

    async def allowed() -> None:
        return None

    monkeypatch.setattr(dataset_scope, "refuse_writing_in_an_unconverted_case", allowed)
    merged, refused = await _write_node("theirs", _nobody_holds)
    assert refused is None and merged.nodes["theirs"].datasets == ["src"]
    linked, refused = await _write_link("theirs", _nobody_holds)
    assert refused is None and linked.committed_edges[0].target == "theirs"


async def test_the_early_check_refuses_before_the_candidate_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15 for the early check alone: removed, the question accept reaches `accept_candidate`,
    which the stamping graph's last word then refuses; with it, the candidate is never read."""
    from services.api import review

    async def unchecked() -> None:
        return None

    monkeypatch.setattr(questions_module, "refuse_writing_in_an_unconverted_case", unchecked)
    reviewed: list[str] = []
    real = review.accept_candidate

    async def counted(*args: Any, **kwargs: Any) -> Any:
        reviewed.append("asked")
        return await real(*args, **kwargs)

    monkeypatch.setattr(questions_module, "accept_candidate", counted)
    _, outcome = await _accept_a_proposal("source")
    assert isinstance(outcome, TouchesTheOriginalsWorkError)
    assert reviewed == ["asked"]  # with the early check, the candidate is never reached

