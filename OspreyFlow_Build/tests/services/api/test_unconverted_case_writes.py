"""A branch's unnamed writes never reach its original case through the source (L3.2 item 3, from
L3.1's final review; ADR-144 Amendment 1).

A case made from another before L3.2 reads its original's dataset and, for a reader holding a level
on the original, the original's layer, until `scripts.migrate_branches_to_views` turns it into a
view. A write naming no dataset there (an accepted proposal's `MENTIONED_IN`, an accepted
extraction, a rule's `ALERTED_ON`) is stamped into the source, which the original reads too.
Linking to, or merging into, a node of the original's own layer would put the original's analysts
in front of work done somewhere else. The stamping graph's last word refuses it, before anything is
written (`TouchesTheOriginalsWorkError`).

What a mistake here would do, and the case that catches it:

- an accepted proposal or email extraction in such a case linking its new node to a Document in
  the original's layer, through the real `QuestionsService` and `EmailExtractionService`:
  `test_an_accepted_proposal_touching_the_originals_work_is_refused`;
- an `ALERTED_ON`, or any link naming no dataset, to a node of that layer:
  `test_a_link_naming_no_dataset_to_the_originals_work_is_refused`;
- a node naming no dataset merging into one of that layer (the source added to its datasets, so the
  layer's node is in the source): `test_a_node_merging_into_the_originals_work_is_refused`;
- each red with the check alone removed:
  `test_each_write_lands_with_the_check_alone_removed`;
- the check refusing what touches only the source:
  `test_a_write_touching_only_the_source_goes_ahead`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api import email_extraction as email_module
from services.api import questions as questions_module
from services.api.dataset_scope import (
    DatasetStampingGraph,
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
#: The email the questions and the extraction read, an event of the case made from the original.
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


ACCEPT_PATHS = pytest.mark.parametrize(
    "accept", [_accept_a_proposal, _accept_from_an_email], ids=["question", "email"]
)


@ACCEPT_PATHS
async def test_an_accepted_proposal_touching_the_originals_work_is_refused(accept: Any) -> None:
    """Refused before anything is written: no node, no link."""
    inner, outcome = await accept("layer")
    assert isinstance(outcome, TouchesTheOriginalsWorkError)
    assert "waiting to become a view" in str(outcome)
    assert inner.committed_edges == []
    assert not [n for n in inner.nodes.values() if n.type == "Person"]


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


async def _write_link(to: str) -> tuple[WritingGraph, Exception | None]:
    store, layer, _ = await _a_case_made_from_another()
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


async def test_a_link_naming_no_dataset_to_the_originals_work_is_refused() -> None:
    inner, refused = await _write_link("theirs")
    assert refused is not None
    assert inner.committed_edges == []


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


async def _write_node(node_id: str) -> tuple[WritingGraph, Exception | None]:
    store, layer, _ = await _a_case_made_from_another()
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


async def test_a_node_merging_into_the_originals_work_is_refused() -> None:
    inner, refused = await _write_node("theirs")
    assert refused is not None
    assert inner.nodes == {}


async def test_a_write_touching_only_the_source_goes_ahead() -> None:
    """The check refuses only what touches the original's layer: a proposal on a source Document,
    an `ALERTED_ON` to a loaded node and a new node are written into the source, as before."""
    for accept in (_accept_a_proposal, _accept_from_an_email):
        inner, accepted = await accept("source")
        assert not isinstance(accepted, Exception)
        assert _mention_of(inner, accepted).datasets == ["src"]
        assert {d for e in inner.committed_edges for d in e.datasets} == {"src"}
    linked, refused = await _write_link("loaded")
    assert refused is None and [e.datasets for e in linked.committed_edges] == [["src"]]
    fresh, refused = await _write_node("new-one")
    assert refused is None and fresh.nodes["new-one"].datasets == ["src"]


async def test_each_write_lands_with_the_check_alone_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red: the layer check removed (the stamping graph's last word, and the same helper
    the two accept paths ask first), each write lands in the source, touching the original's
    layer, where the original's analysts would see it."""

    async def allowed(self: Any, node_ids: Any, **_: Any) -> None:
        return None

    async def unchecked(graph: Any, node_ids: Any, **_: Any) -> None:
        return None

    monkeypatch.setattr(DatasetStampingGraph, "_refuse_touching_a_read_only_layer", allowed)
    monkeypatch.setattr(questions_module, "refuse_touching_a_read_only_layer", unchecked)
    monkeypatch.setattr(email_module, "refuse_touching_a_read_only_layer", unchecked)
    for accept in (_accept_a_proposal, _accept_from_an_email):
        inner, accepted = await accept("layer")
        assert not isinstance(accepted, Exception)
        mention = _mention_of(inner, accepted)
        assert mention.datasets == ["src"] and mention.target == email_document_id("ev-1")
    linked, refused = await _write_link("theirs")
    assert refused is None and linked.committed_edges[0].target == "theirs"
    merged, refused = await _write_node("theirs")
    assert refused is None and merged.nodes["theirs"].datasets == ["src"]


# --- a member holding no level on the original (the lane review's blocker 2, rule 3) -----------


async def _a_strangers_link(to: str) -> Exception | None:
    store, layer, _ = await _a_case_made_from_another(_nobody_holds)
    inner = _held(
        _ReadsBack(),
        node("theirs").model_copy(update={"datasets": [layer]}),
        node("loaded").model_copy(update={"datasets": ["src"]}),
    )
    graph = stamping(inner, registry=store)
    tx = await graph.begin_transaction()
    try:
        await graph.upsert_nodes([_merging("alert-1")], tx)
        await graph.upsert_edges([_alerted_on(to)], tx)
    except TouchesTheOriginalsWorkError as refused:
        await graph.rollback_transaction(tx)
        return refused
    await graph.rollback_transaction(tx)
    return None


async def test_a_stranger_is_answered_alike_for_the_originals_node_and_a_missing_one() -> None:
    """A member of the made case alone reads none of the original's layer. A link to its node and
    a link to an id nobody holds are refused in the same words, so the answer says nothing about
    the layer; a link to a node they read goes ahead."""
    theirs, missing = await _a_strangers_link("theirs"), await _a_strangers_link("never-held")
    assert theirs is not None and missing is not None and str(theirs) == str(missing)
    assert await _a_strangers_link("loaded") is None


async def test_a_document_the_stranger_reads_in_the_source_is_not_refused() -> None:
    """A Document in the source and in the original's layer is read by the stranger through the
    source: accepting a proposal on it goes ahead, as it does on any source Document, so the
    answer cannot tell them the original's analysts also hold it."""
    inner, accepted = await _accept_a_proposal("both", _nobody_holds)
    assert not isinstance(accepted, Exception)
    assert _mention_of(inner, accepted).datasets == ["src"]


async def test_the_stranger_check_fails_with_the_layer_read_whatever_they_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red: the check as it was, looking in the original's layer as the writer whatever
    they hold there, refuses the stranger on the shared Document: the leak the review found."""
    from services.api import dataset_scope

    async def as_it_was(graph: Any, node_ids: Any, **_: Any) -> None:
        scope = dataset_scope._CASE_SCOPE.get()
        layer = dataset_scope._READ_ONLY_LAYER.get()
        if layer is None or scope is None:
            return
        in_the_layer = scope[2].model_copy(update={"datasets": [layer]})
        if await graph.get_nodes(sorted(set(node_ids)), in_the_layer):
            raise TouchesTheOriginalsWorkError

    monkeypatch.setattr(dataset_scope, "refuse_touching_a_read_only_layer", as_it_was)
    monkeypatch.setattr(questions_module, "refuse_touching_a_read_only_layer", as_it_was)
    _, accepted = await _accept_a_proposal("both", _nobody_holds)
    assert isinstance(accepted, TouchesTheOriginalsWorkError)


async def test_without_the_early_check_a_proposal_leaves_an_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15 for the early check alone: with only the stamping graph's last word left, the
    question accept commits its Person before the link is refused, an orphan in the source with
    the candidate marked accepted, which is why the accept paths ask first."""

    async def unchecked(graph: Any, node_ids: Any, **_: Any) -> None:
        return None

    monkeypatch.setattr(questions_module, "refuse_touching_a_read_only_layer", unchecked)
    inner, outcome = await _accept_a_proposal("layer")
    assert isinstance(outcome, TouchesTheOriginalsWorkError)
    assert inner.committed_edges == []
    assert [n.datasets for n in inner.nodes.values() if n.type == "Person"] == [["src"]]
