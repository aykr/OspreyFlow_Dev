"""Changing a link — `06_DECISIONS.md` ADR-080. The service's own rules, against
`FakeWorkingSetStore`, an in-memory change store and a graph stand-in that refuses what
`GraphPort.supersede_edge` refuses (`CLAUDE.md` rule 15). The real Postgres store has its own
file (`test_link_changes_store.py`, owner-run like the other store tests).

The sentences under test:

* A link is changed by *superseding* it: the old link is kept, marked as replaced, and a new link
  with the change stands in the working set in its place. Nothing is edited in place.
* Every change records who, when, why and the old and new values, and the reason is required.
* Only someone who can see the link may change it or read its history; a link they cannot see
  answers exactly as one that does not exist (rules 3 and 4).
* Same-as / not-the-same links are not changed here: resolution has its own routes, and changing
  one by hand would let the clusters and the links disagree (rule 6).
* A note on the old link follows the link to its replacement.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.link_changes import (
    ChangeNotMadeError,
    InvalidChangeError,
    LinkChange,
    LinkChangeRequest,
    LinkChangeService,
    LinkChangeStorage,
    ResolutionLinkError,
)
from services.api.link_notes import LinkNotFoundError
from services.api.working_set.models import DeltaReplaceEdge
from services.api.working_set.service import WorkingSetService

from ontology.errors import OntologyError
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeId,
    EdgeTypeDef,
    EdgeWrite,
    EntityTypeDef,
    Handling,
    Interval,
    Node,
    OntologySchema,
    PoleClass,
    Principal,
    PropertyDef,
    PropertyType,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
    TxId,
)

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME

ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
CLEARED = Principal(id="analyst-3", clearance="SECRET", org_unit="unit-1")

ONTOLOGY = OntologySchema(
    version=1,
    entity_types=[
        EntityTypeDef(name="Person", pole_class=PoleClass.PERSON, channel="indigo", shape="circle"),
        EntityTypeDef(
            name="Organisation", pole_class=PoleClass.OBJECT, channel="cyan", shape="square"
        ),
    ],
    edge_types=[
        EdgeTypeDef(name="ASSOCIATE_OF", **{"from": ["Person"], "to": ["Person"]}, basis="direct"),
        EdgeTypeDef(
            name="FAMILY_OF",
            **{"from": ["Person"], "to": ["Person"]},
            properties=[PropertyDef(name="relation", type=PropertyType.STRING)],
            basis="direct",
        ),
        EdgeTypeDef(
            name="MEMBER_OF", **{"from": ["Person"], "to": ["Organisation"]}, basis="direct"
        ),
        EdgeTypeDef(
            name="MET_AT", **{"from": ["Person"], "to": ["Person"]}, temporal=True, basis="direct"
        ),
        EdgeTypeDef(
            name="LIKELY_ASSOCIATE_OF",
            **{"from": ["Person"], "to": ["Person"]},
            basis="probabilistic",
        ),
        EdgeTypeDef(
            name="SAME_AS", **{"from": ["*"], "to": ["*"]}, system=True, basis="probabilistic"
        ),
        EdgeTypeDef(name="NOT_SAME_AS", **{"from": ["*"], "to": ["*"]}, system=True),
    ],
)


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification, handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _node(node_id: str, type_: str = "Person", classification: str = "OFFICIAL") -> Node:
    return Node(
        id=node_id,
        type=type_,
        provenance=_provenance(),
        handling=_handling(classification),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="fixture"),
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    type_: str = "ASSOCIATE_OF",
    classification: str = "OFFICIAL",
    **extra: Any,
) -> Edge:
    return Edge(
        id=edge_id,
        type=type_,
        source=source,
        target=target,
        provenance=_provenance(),
        handling=_handling(classification),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="fixture"),
        **extra,
    )


class SupersedingGraph(FakeGraphPort):
    """Refuses what the adapter's `supersede_edge` refuses: an edge that is not stored, a type the
    ontology does not hold, properties the type does not declare — and keeps nothing a rolled-back
    transaction wrote."""

    def __init__(self, stored_edge_ids: set[str]) -> None:
        super().__init__(Subgraph(nodes=[], edges=[]))
        self.stored = set(stored_edge_ids)
        self.superseded: list[tuple[EdgeId, EdgeWrite]] = []
        self._pending: dict[TxId, list[tuple[EdgeId, EdgeWrite]]] = {}
        self.fail_with: Exception | None = None

    async def begin_transaction(self) -> TxId:
        tx = await super().begin_transaction()
        self._pending[tx] = []
        return tx

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        if self.fail_with is not None:
            raise self.fail_with
        if edge_id not in self.stored:
            raise OntologyError(f"cannot supersede {edge_id!r}: no such edge")
        if ONTOLOGY.edge_type(replacement.type) is None:
            raise OntologyError(f"{replacement.type!r} is not a type in the active ontology")
        self._pending[tx].append((edge_id, replacement))
        return replacement.id

    async def commit_transaction(self, tx: TxId) -> None:
        for old, write in self._pending.pop(tx, []):
            self.superseded.append((old, write))
            self.stored.add(write.id)
        await super().commit_transaction(tx)

    async def rollback_transaction(self, tx: TxId) -> None:
        self._pending.pop(tx, None)
        await super().rollback_transaction(tx)


class InMemoryChanges:
    def __init__(self) -> None:
        self.rows: list[LinkChange] = []

    async def add(self, change: LinkChange) -> None:
        self.rows.append(change)

    async def produced(self, investigation_id: str, edge_id: str) -> LinkChange | None:
        for row in self.rows:
            if row.investigation_id == investigation_id and row.edge_id == edge_id:
                return row
        return None


class MovedNotes:
    """Records the notes move; the real store's own test proves the SQL."""

    def __init__(self) -> None:
        self.moves: list[tuple[str, str, str]] = []

    async def rekey(self, investigation_id: str, old_edge_id: str, new_edge_id: str) -> int:
        self.moves.append((investigation_id, old_edge_id, new_edge_id))
        return 1


async def _build(
    edges: Sequence[Edge] | None = None,
) -> tuple[LinkChangeService, SupersedingGraph, FakeWorkingSetStore, InMemoryChanges, MovedNotes]:
    store = FakeWorkingSetStore()
    await store.add_nodes(
        "inv-1",
        [
            _node("a"),
            _node("b"),
            _node("org", "Organisation"),
            _node("c", classification="SECRET"),
        ],
    )
    link_set = list(
        edges
        if edges is not None
        else [
            _edge("e1", "a", "b", occurrences=3),
            _edge("sa", "a", "b", "SAME_AS"),
            _edge("ns", "a", "b", "NOT_SAME_AS"),
            _edge("m1", "a", "org", "MEMBER_OF"),
            _edge("secret-link", "a", "b", classification="SECRET"),
            _edge("secret-end", "a", "c"),
            # ADR-081 step B: a link of a Direct type an analyst has marked probabilistic, and a
            # link of a Probabilistic type.
            _edge("marked", "a", "b", basis="probabilistic"),
            _edge("likely", "a", "b", "LIKELY_ASSOCIATE_OF"),
        ]
    )
    await store.add_edges("inv-1", link_set)
    graph = SupersedingGraph({e.id for e in link_set})
    changes = InMemoryChanges()
    notes = MovedNotes()
    storage: LinkChangeStorage = changes
    service = LinkChangeService(
        storage, WorkingSetService(graph, store, SCHEME), graph, ONTOLOGY, notes
    )
    return service, graph, store, changes, notes


async def test_changing_the_type_replaces_the_link_and_keeps_the_old_one() -> None:
    service, graph, store, _, _ = await _build()
    result = await service.change(
        "inv-1",
        "e1",
        ANALYST,
        LinkChangeRequest(type="FAMILY_OF", properties={"relation": "cousin"}, reason="Told so"),
    )
    new = result.edge
    assert new.id != "e1"
    assert new.type == "FAMILY_OF"
    assert new.properties == {"relation": "cousin"}
    assert (new.source, new.target) == ("a", "b")
    # The graph was asked to supersede, not to overwrite: one superseded pair, old id named.
    assert [old for old, _ in graph.superseded] == ["e1"]
    # The working set now holds the new link and not the old one.
    assert await store.get_edge("inv-1", "e1") is None
    assert (await store.get_edge("inv-1", new.id)) is not None
    assert isinstance(result.delta, DeltaReplaceEdge)
    assert result.delta.old_edge_id == "e1"
    assert result.delta.edge.id == new.id


async def test_the_new_link_is_attributed_to_the_analyst_and_counts_as_a_revision() -> None:
    service, graph, _, _, _ = await _build()
    result = await service.change(
        "inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
    )
    assert result.edge.audit.created_by == ANALYST.id
    assert result.edge.audit.revision == 2
    assert result.edge.provenance.state is ProvenanceState.ASSERTED
    # What the link was built from is kept, with the analyst's change added to it.
    documents = [s.document_id for s in result.edge.provenance.sources]
    assert documents[0] == "doc-1"
    assert any(d.startswith("manual:change:e1") for d in documents)
    written = graph.superseded[0][1]
    assert written.created_by == ANALYST.id
    assert written.handling == _handling()  # a change never alters the marking


async def test_details_can_change_without_the_type_changing() -> None:
    service, _, _, _, _ = await _build()
    result = await service.change(
        "inv-1", "e1", ANALYST, LinkChangeRequest(occurrences=7, reason="Seen four more times")
    )
    assert result.edge.type == "ASSOCIATE_OF"
    assert result.edge.occurrences == 7


async def test_a_validity_period_can_be_set_and_then_cleared() -> None:
    service, _, _, _, _ = await _build([_edge("t1", "a", "b", "MET_AT")])
    first = await service.change(
        "inv-1",
        "t1",
        ANALYST,
        LinkChangeRequest(
            interval=Interval(valid_from=datetime(2026, 3, 1, tzinfo=UTC)), reason="Dated"
        ),
    )
    assert first.edge.interval is not None
    second = await service.change(
        "inv-1", first.edge.id, ANALYST, LinkChangeRequest(interval=None, reason="Undated again")
    )
    assert second.edge.interval is None


async def test_the_reason_is_required() -> None:
    service, graph, store, _, _ = await _build()
    for reason in ("", "   "):
        with pytest.raises(InvalidChangeError, match="reason"):
            await service.change(
                "inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason=reason)
            )
    assert graph.superseded == []
    assert await store.get_edge("inv-1", "e1") is not None


async def test_a_change_that_changes_nothing_is_refused() -> None:
    service, graph, _, _, _ = await _build()
    with pytest.raises(ChangeNotMadeError):
        await service.change(
            "inv-1", "e1", ANALYST, LinkChangeRequest(type="ASSOCIATE_OF", reason="Same")
        )
    assert graph.superseded == []


@pytest.mark.parametrize(
    ("request_", "message"),
    [
        (LinkChangeRequest(type="NO_SUCH_TYPE", reason="r"), "NO_SUCH_TYPE"),
        # MEMBER_OF runs Person -> Organisation; e1 joins two people.
        (LinkChangeRequest(type="MEMBER_OF", reason="r"), "MEMBER_OF"),
        # ASSOCIATE_OF declares no `colour`.
        (LinkChangeRequest(properties={"colour": "red"}, reason="r"), "colour"),
        (LinkChangeRequest(occurrences=0, reason="r"), "occurrences"),
    ],
)
async def test_a_change_the_ontology_would_refuse_is_refused_before_anything_is_written(
    request_: LinkChangeRequest, message: str
) -> None:
    service, graph, store, changes, _ = await _build()
    with pytest.raises(InvalidChangeError, match=message):
        await service.change("inv-1", "e1", ANALYST, request_)
    assert graph.superseded == []
    assert changes.rows == []
    assert await store.get_edge("inv-1", "e1") is not None


@pytest.mark.parametrize("link_id", ["sa", "ns"])
async def test_same_as_and_not_the_same_links_are_not_changed_here(link_id: str) -> None:
    service, graph, _, _, _ = await _build()
    with pytest.raises(ResolutionLinkError):
        await service.change(
            "inv-1", link_id, ANALYST, LinkChangeRequest(type="ASSOCIATE_OF", reason="r")
        )
    assert graph.superseded == []


async def test_a_link_cannot_be_changed_into_a_same_as_link() -> None:
    service, graph, _, _, _ = await _build()
    with pytest.raises(ResolutionLinkError):
        await service.change("inv-1", "e1", ANALYST, LinkChangeRequest(type="SAME_AS", reason="r"))
    assert graph.superseded == []


async def test_the_change_is_recorded_with_who_when_why_and_old_and_new_values() -> None:
    service, _, _, changes, _ = await _build()
    result = await service.change(
        "inv-1",
        "e1",
        ANALYST,
        LinkChangeRequest(type="FAMILY_OF", properties={"relation": "cousin"}, reason="Told so"),
    )
    [row] = changes.rows
    assert row.edge_id == result.edge.id
    assert row.previous_edge_id == "e1"
    assert row.changed_by == ANALYST.id
    assert row.reason == "Told so"
    assert row.before["type"] == "ASSOCIATE_OF"
    assert row.before["occurrences"] == 3
    assert row.after["type"] == "FAMILY_OF"
    assert row.after["properties"] == {"relation": "cousin"}
    assert row.changed_at.tzinfo is not None


async def test_the_history_follows_a_link_back_through_every_change() -> None:
    service, _, _, _, _ = await _build()
    first = await service.change(
        "inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="First")
    )
    second = await service.change(
        "inv-1",
        first.edge.id,
        ANALYST,
        LinkChangeRequest(properties={"relation": "sister"}, reason="Second"),
    )
    history = (await service.history("inv-1", second.edge.id, ANALYST)).changes
    assert [c.reason for c in history] == ["Second", "First"]  # newest first
    assert [c.previous_edge_id for c in history] == [first.edge.id, "e1"]


async def test_a_link_nobody_changed_has_an_empty_history() -> None:
    service, _, _, _, _ = await _build()
    assert (await service.history("inv-1", "e1", ANALYST)).changes == []


async def test_notes_on_the_old_link_follow_it_to_the_new_one() -> None:
    service, _, _, _, notes = await _build()
    result = await service.change(
        "inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="Told so")
    )
    assert notes.moves == [("inv-1", "e1", result.edge.id)]


async def test_a_failure_in_the_graph_leaves_the_working_set_and_history_untouched() -> None:
    service, graph, store, changes, notes = await _build()
    graph.fail_with = OntologyError("the store said no")
    with pytest.raises(OntologyError):
        await service.change(
            "inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="r")
        )
    assert await store.get_edge("inv-1", "e1") is not None
    assert changes.rows == []
    assert notes.moves == []


# --- access control (CLAUDE.md rules 3 and 4): every path answers a link the principal cannot
# --- see exactly as it answers a link that does not exist.


@pytest.mark.parametrize("link_id", ["no-such-link", "secret-link", "secret-end"])
async def test_changing_a_link_the_principal_cannot_see_is_indistinguishable_from_missing(
    link_id: str,
) -> None:
    service, graph, store, changes, _ = await _build()
    before = await store.get_edge("inv-1", link_id)
    with pytest.raises(LinkNotFoundError):
        await service.change(
            "inv-1", link_id, ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="r")
        )
    assert graph.superseded == []
    assert changes.rows == []
    assert await store.get_edge("inv-1", link_id) == before


@pytest.mark.parametrize("link_id", ["no-such-link", "secret-link", "secret-end"])
async def test_reading_the_history_of_a_link_the_principal_cannot_see_is_indistinguishable(
    link_id: str,
) -> None:
    service, _, _, _, _ = await _build()
    with pytest.raises(LinkNotFoundError):
        await service.history("inv-1", link_id, ANALYST)


async def test_a_history_is_not_readable_from_another_investigation() -> None:
    service, _, _, _, _ = await _build()
    await service.change("inv-1", "e1", ANALYST, LinkChangeRequest(type="FAMILY_OF", reason="r"))
    with pytest.raises(LinkNotFoundError):
        await service.history("inv-2", "e1", ANALYST)


async def test_someone_cleared_for_the_marking_can_change_that_link() -> None:
    service, _, _, _, _ = await _build()
    result = await service.change(
        "inv-1", "secret-link", CLEARED, LinkChangeRequest(type="FAMILY_OF", reason="r")
    )
    assert result.edge.handling.classification == "SECRET"


# --- the link's own basis (ADR-081 step B) -----------------------------------------------------


async def test_marking_a_link_of_a_direct_type_probabilistic_is_written_and_recorded() -> None:
    service, graph, _, changes, _ = await _build()
    result = await service.change(
        "inv-1",
        "e1",
        ANALYST,
        LinkChangeRequest(basis="probabilistic", reason="The pairing is inferred from timing."),
    )
    assert result.edge.basis == "probabilistic"
    written = graph.superseded[0][1]
    assert written.basis == "probabilistic"
    # The history shows what stood behind the link before and after, so the reason the analyst
    # gave is the reason for the mark (Amendment 2).
    assert changes.rows[0].before["basis"] == "direct"
    assert changes.rows[0].after["basis"] == "probabilistic"
    assert changes.rows[0].reason == "The pairing is inferred from timing."


async def test_a_link_of_a_probabilistic_type_cannot_be_marked_direct() -> None:
    service, graph, _, _, _ = await _build()
    with pytest.raises(InvalidChangeError, match="[Dd]irect"):
        await service.change(
            "inv-1", "likely", ANALYST, LinkChangeRequest(basis="direct", reason="Told so")
        )
    assert graph.superseded == []


async def test_a_probabilistic_link_is_never_returned_to_direct() -> None:
    # "A link is never promoted to Direct by a person" (ADR-081 decision 2), whether the mark was
    # the analyst's own or the type's.
    service, graph, _, _, _ = await _build()
    with pytest.raises(InvalidChangeError, match="[Dd]irect"):
        await service.change(
            "inv-1", "marked", ANALYST, LinkChangeRequest(basis="direct", reason="Told so")
        )
    # Changing a Probabilistic-type link to a Direct type must not quietly make it Direct either.
    with pytest.raises(InvalidChangeError, match="[Dd]irect"):
        await service.change(
            "inv-1",
            "likely",
            ANALYST,
            LinkChangeRequest(type="ASSOCIATE_OF", basis="direct", reason="Told so"),
        )
    assert graph.superseded == []


async def test_a_probabilistic_mark_follows_the_link_through_a_type_change() -> None:
    service, graph, _, _, _ = await _build()
    result = await service.change(
        "inv-1",
        "marked",
        ANALYST,
        LinkChangeRequest(type="FAMILY_OF", properties={"relation": "cousin"}, reason="Told so"),
    )
    assert result.edge.type == "FAMILY_OF"
    assert result.edge.basis == "probabilistic"
    assert graph.superseded[0][1].basis == "probabilistic"


async def test_a_probabilistic_type_link_changed_to_a_direct_type_stays_probabilistic() -> None:
    # With no basis asked for, the link keeps what stood behind it: it was probabilistic by its
    # type, so it is written with the mark once its new type would otherwise call it Direct.
    service, graph, _, _, _ = await _build()
    result = await service.change(
        "inv-1", "likely", ANALYST, LinkChangeRequest(type="ASSOCIATE_OF", reason="Told so")
    )
    assert result.edge.basis == "probabilistic"
    assert graph.superseded[0][1].basis == "probabilistic"


async def test_asking_for_the_basis_a_link_already_has_changes_nothing() -> None:
    service, graph, _, _, _ = await _build()
    with pytest.raises(ChangeNotMadeError):
        await service.change(
            "inv-1", "e1", ANALYST, LinkChangeRequest(basis="direct", reason="Told so")
        )
    with pytest.raises(ChangeNotMadeError):
        await service.change(
            "inv-1", "marked", ANALYST, LinkChangeRequest(basis="probabilistic", reason="Told so")
        )
    assert graph.superseded == []


async def test_retyping_a_direct_link_to_a_probabilistic_type_makes_it_probabilistic() -> None:
    """Found building ADR-090: with no basis asked for, the kept one was Direct, and the change was
    refused as marking a probabilistic type Direct, though the analyst asked for no such thing."""
    service, _, _, _, _ = await _build()
    result = await service.change(
        "inv-1", "e1", ANALYST, LinkChangeRequest(type="LIKELY_ASSOCIATE_OF", reason="Less sure")
    )
    assert result.edge.type == "LIKELY_ASSOCIATE_OF"
    assert result.change.after["basis"] == "probabilistic"


# --- ADR-102 decision 4: handling is changed on purpose, and lowered only by an Author --------

from services.api.link_changes import (  # noqa: E402
    LoweringNeedsAuthorError,
    LoweringNotConfirmedError,
)

OFFICIAL_SENSITIVE = Handling(
    classification="OFFICIAL-SENSITIVE",
    handling_code="P",
    originator="unit-1",
    owning_unit="unit-1",
)


async def _service_with_scheme() -> tuple[LinkChangeService, SupersedingGraph, InMemoryChanges]:
    service, graph, store, changes, notes = await _build()
    with_scheme = LinkChangeService(
        changes, WorkingSetService(graph, store, SCHEME), graph, ONTOLOGY, notes, scheme=SCHEME
    )
    return with_scheme, graph, changes


async def test_an_editor_may_raise_a_links_handling() -> None:
    service, graph, changes = await _service_with_scheme()
    result = await service.change(
        "inv-1", "e1", CLEARED, LinkChangeRequest(handling=OFFICIAL_SENSITIVE, reason="Sensitive")
    )
    assert graph.superseded[0][1].handling == OFFICIAL_SENSITIVE
    assert result.edge.handling == OFFICIAL_SENSITIVE
    assert changes.rows[0].before["handling"]["classification"] == "OFFICIAL"
    assert changes.rows[0].after["handling"]["classification"] == "OFFICIAL-SENSITIVE"


@pytest.mark.parametrize(
    "lower",
    [
        _handling("OFFICIAL"),  # the classification
        _handling("SECRET").model_copy(update={"handling_code": "P"}),  # the handling code
        _handling("SECRET").model_copy(update={"handling_code": "C"}),  # the action code dropped
    ],
)
async def test_lowering_needs_an_author_and_a_confirmation(lower: Handling) -> None:
    secret = _handling("SECRET").model_copy(update={"handling_code": "C", "action_code": "A1"})
    held = _edge("s1", "a", "b").model_copy(update={"handling": secret})
    _, graph, store, changes, notes = await _build([held])
    service = LinkChangeService(
        changes, WorkingSetService(graph, store, SCHEME), graph, ONTOLOGY, notes, scheme=SCHEME
    )
    request = LinkChangeRequest(handling=lower, reason="Released by the originator")
    with pytest.raises(LoweringNeedsAuthorError):
        await service.change("inv-1", "s1", CLEARED, request)
    with pytest.raises(LoweringNotConfirmedError):
        await service.change("inv-1", "s1", CLEARED, request, is_author=True)
    assert graph.superseded == [] and changes.rows == []
    confirmed = request.model_copy(update={"confirm_lower": True})
    result = await service.change("inv-1", "s1", CLEARED, confirmed, is_author=True)
    assert result.edge.handling == lower
    assert graph.superseded[0][1].handling == lower


async def test_handling_keeps_its_units_and_stays_within_the_analysts_clearance() -> None:
    service, graph, _ = await _service_with_scheme()
    moved = _handling().model_copy(update={"owning_unit": "unit-2"})
    with pytest.raises(InvalidChangeError, match="unit"):
        await service.change("inv-1", "e1", CLEARED, LinkChangeRequest(handling=moved, reason="x"))
    above = _handling("SECRET")
    with pytest.raises(InvalidChangeError, match="clearance"):
        await service.change("inv-1", "e1", ANALYST, LinkChangeRequest(handling=above, reason="x"))
    unknown = _handling().model_copy(update={"handling_code": "Z"})
    with pytest.raises(InvalidChangeError):
        await service.change(
            "inv-1", "e1", CLEARED, LinkChangeRequest(handling=unknown, reason="x")
        )
    assert graph.superseded == []
