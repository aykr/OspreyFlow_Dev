"""The document reader never sends an email's end nodes or link to a reader who may not see them
(SE9d; rules 1, 3 and 4). An event is read on its own handling, and its link's ends, or the link,
may be marked above the reader, so an id copied from the event can name what they may not see.

The rule: `sender_id` and `recipient_id` only where `visible_node` would give that node to the
reader in this case; `edge_id` and `event_id` only where `visible_edge` would give the link, which
it never does with a hidden end. Otherwise each is `None`, and the answer is the one given for an
end that is not in the case at all.

The cases are the slice's table. The ids are long ones, so that "not anywhere in the answer" can be
asked of the whole of it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.app import read_document_route
from services.api.document_reader import Designation, DocumentReaderService, DocumentReaderView
from services.api.email_extraction import email_document_id
from services.api.link_events import LinkEventsService
from services.api.link_notes import LinkNotFoundError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Node, Principal

from .case_dataset import in_a_case_with_a_layer  # noqa: F401 (a fixture)
from .test_document_reader import _document
from .test_email_extraction import (
    ANALYST,
    TEXT,
    InMemoryCandidates,
    RecordingAnalytics,
    WritingGraph,
    _event,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

#: The event's own ends, and its link: the link runs from the first to the second.
SOURCE = "node-source-7f3a"
TARGET = "node-target-3c9b"
LINK = "link-email-9d2e"
EVENT = "ev-1"
DOCUMENT = email_document_id(EVENT)
IDS = ("sender_id", "recipient_id", "edge_id", "event_id")
CLEARED = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1")


class ReadRecordingStore(FakeWorkingSetStore):
    """Keeps every read of a body, in order, with the ids it asked for."""

    def __init__(self) -> None:
        super().__init__()
        self.reads: list[tuple[Any, ...]] = []

    async def get_node(self, investigation_id: str, node_id: str) -> Node | None:
        self.reads.append(("get_node", node_id))
        return await super().get_node(investigation_id, node_id)

    async def get_edge(self, investigation_id: str, edge_id: str) -> Any:
        self.reads.append(("get_edge", edge_id))
        return await super().get_edge(investigation_id, edge_id)

    async def get_members(
        self, investigation_id: str, node_ids: Sequence[str], edge_ids: Sequence[str]
    ) -> Any:
        self.reads.append(("get_members", tuple(node_ids), tuple(edge_ids)))
        return await super().get_members(investigation_id, node_ids, edge_ids)  # type: ignore[misc]


async def _world(
    *,
    source: str | None = "OFFICIAL",
    target: str | None = "OFFICIAL",
    link: str | None = "OFFICIAL",
    direction: str = "outbound",
) -> tuple[DocumentReaderService, ReadRecordingStore]:
    """One email on a link in the case. Each of the link and its two ends is stored at the
    classification given, or, at `None`, is not in the case at all."""
    store = ReadRecordingStore()
    ends = [node(i, c) for i, c in ((SOURCE, source), (TARGET, target)) if c is not None]
    await store.add_nodes("inv-1", [*ends, _document(DOCUMENT, event_id=EVENT)])
    if link is not None:
        await store.add_edges("inv-1", [edge(LINK, SOURCE, TARGET, link)])
    mail = _event(EVENT, LINK).model_copy(
        update={"source_id": SOURCE, "target_id": TARGET, "direction": direction}
    )
    graph = WritingGraph()
    reader = DocumentReaderService(
        WorkingSetService(graph, store, SCHEME),
        RecordingAnalytics([mail]),  # type: ignore[arg-type]
        graph,
        InMemoryCandidates(),  # type: ignore[arg-type]
    )
    return reader, store


async def _read(principal: Principal = ANALYST, **world: Any) -> DocumentReaderView:
    reader, _ = await _world(**world)
    return await reader.read("inv-1", DOCUMENT, principal)


def _ids(view: DocumentReaderView) -> tuple[str | None, ...]:
    return tuple(getattr(view, name) for name in IDS)


def _the_rest_is_the_email(view: DocumentReaderView) -> None:
    assert (view.document_id, view.title, view.text) == (DOCUMENT, "Dabhol", TEXT)
    assert view.sent_at == _event(EVENT).occurred_at
    assert (view.truncated, view.spans, view.has_file) == (False, [], False)


# 1, 2: an end above the reader. Its link goes with it: `visible_edge` gives no link that has an
# end the reader may not see.


async def test_a_sender_above_the_reader_is_not_sent() -> None:
    view = await _read(source="SECRET")
    assert _ids(view) == (None, TARGET, None, None)
    answer = view.model_dump_json()
    assert SOURCE not in answer and LINK not in answer
    _the_rest_is_the_email(view)


async def test_a_recipient_above_the_reader_is_not_sent() -> None:
    view = await _read(target="SECRET")
    assert _ids(view) == (SOURCE, None, None, None)
    answer = view.model_dump_json()
    assert TARGET not in answer and LINK not in answer
    _the_rest_is_the_email(view)


async def test_an_end_in_a_dataset_the_case_does_not_read_is_not_sent() -> None:
    """`visible_node` judges datasets too: the end must be the reader's in this case."""
    reader, store = await _world()
    elsewhere = node(SOURCE).model_copy(update={"datasets": ["another-case"]})
    await store.add_nodes("inv-1", [elsewhere])
    for member in (DOCUMENT, TARGET):
        held = store._n("inv-1")[member]
        await store.add_nodes("inv-1", [held.model_copy(update={"datasets": ["this-case"]})])
    link = store._e("inv-1")[LINK]
    await store.add_edges("inv-1", [link.model_copy(update={"datasets": ["this-case"]})])
    in_case = ANALYST.model_copy(update={"datasets": ["this-case"]})
    view = await reader.read("inv-1", DOCUMENT, in_case)
    assert _ids(view) == (None, TARGET, None, None)


# 3: the link above the reader, both its ends theirs.


async def test_a_link_above_the_reader_is_not_sent_though_both_ends_are() -> None:
    view = await _read(link="SECRET")
    assert _ids(view) == (SOURCE, TARGET, None, None)
    assert LINK not in view.model_dump_json()
    _the_rest_is_the_email(view)


# 4: what the reader may see is sent as before.


async def test_ends_and_a_link_the_reader_may_see_are_all_sent() -> None:
    view = await _read()
    assert _ids(view) == (SOURCE, TARGET, LINK, EVENT)
    _the_rest_is_the_email(view)


async def test_a_reader_cleared_for_them_is_sent_all_four() -> None:
    view = await _read(CLEARED, source="SECRET", target="SECRET", link="SECRET")
    assert _ids(view) == (SOURCE, TARGET, LINK, EVENT)


# 5: withheld reads as not there.

HIDDEN_AND_ABSENT = [
    pytest.param({"source": "SECRET"}, {"source": None}, id="sender"),
    pytest.param({"target": "SECRET"}, {"target": None}, id="recipient"),
    pytest.param({"link": "SECRET"}, {"link": None}, id="link"),
]


@pytest.mark.parametrize(("hidden", "absent"), HIDDEN_AND_ABSENT)
async def test_a_withheld_one_answers_byte_for_byte_as_one_not_in_the_case(
    hidden: dict[str, Any], absent: dict[str, Any]
) -> None:
    withheld = (await _read(**hidden)).model_dump_json().encode()
    not_there = (await _read(**absent)).model_dump_json().encode()
    assert withheld == not_there
    # The same fields, in the same order, as an email whose ids are all sent: nothing is added to
    # say that one was withheld, and none is left out.
    everything = (await _read()).model_dump_json()
    assert list(json.loads(withheld)) == list(json.loads(everything))
    assert list(json.loads(withheld)) == list(DocumentReaderView.model_fields)


async def test_every_answer_reads_the_ends_and_the_link_in_the_same_one_read() -> None:
    """No path the reader can tell apart: whether all is theirs, something is above them or
    something is not in the case, the store is asked the same things in the same order, the
    Document first and then the link with both ends in one read."""
    worlds: list[dict[str, Any]] = [
        {},
        {"source": "SECRET"},
        {"target": "SECRET"},
        {"link": "SECRET"},
        {"source": "SECRET", "target": "SECRET", "link": "SECRET"},
        {"source": None},
        {"target": None},
        {"link": None},
    ]
    expected = [("get_node", DOCUMENT), ("get_members", (SOURCE, TARGET), (LINK,))]
    for world in worlds:
        reader, store = await _world(**world)
        await reader.read("inv-1", DOCUMENT, ANALYST)
        assert store.reads == expected, world


# 6: an inbound email was sent by the link's far end, and the rule follows it there.


async def test_an_inbound_emails_hidden_sender_is_the_far_end() -> None:
    view = await _read(target="SECRET", direction="inbound")
    assert _ids(view) == (None, SOURCE, None, None)
    assert TARGET not in view.model_dump_json()


async def test_an_inbound_emails_hidden_recipient_is_the_near_end() -> None:
    view = await _read(source="SECRET", direction="inbound")
    assert _ids(view) == (TARGET, None, None, None)
    assert SOURCE not in view.model_dump_json()


async def test_an_inbound_email_with_both_ends_visible_keeps_them_reversed() -> None:
    view = await _read(direction="inbound")
    assert _ids(view) == (TARGET, SOURCE, LINK, EVENT)


# 7: every other path that sends these ids, or reads through the reader.


class _Audit:
    async def record(self, **_: Any) -> None:
        return None


@pytest.mark.parametrize(
    ("hidden", "secret_id"),
    [({"source": "SECRET"}, SOURCE), ({"target": "SECRET"}, TARGET), ({"link": "SECRET"}, LINK)],
)
async def test_the_route_sends_no_withheld_id(hidden: dict[str, Any], secret_id: str) -> None:
    reader, _ = await _world(**hidden)
    view = await read_document_route(
        investigation=SimpleNamespace(id="inv-1"),  # type: ignore[arg-type]
        document_id=DOCUMENT,
        principal=ANALYST,
        document_reader=reader,
        audit=_Audit(),  # type: ignore[arg-type]
    )
    assert secret_id not in view.model_dump_json()
    assert (view.edge_id, view.event_id) == (None, None)


@pytest.mark.usefixtures("in_a_case_with_a_layer")
@pytest.mark.parametrize(
    ("hidden", "secret_id"), [({"source": "SECRET"}, SOURCE), ({"link": "SECRET"}, LINK)]
)
async def test_marking_words_in_the_email_answers_with_no_withheld_id(
    hidden: dict[str, Any], secret_id: str
) -> None:
    """`designate` reads through the reader and answers with what it wrote."""
    reader, _ = await _world(**hidden)
    start = TEXT.index("Dana MERCER")
    result = await reader.designate(
        "inv-1",
        DOCUMENT,
        Designation(entity_type="Person", text="Dana MERCER", start=start, end=start + 11),
        ANALYST,
    )
    assert secret_id not in result.model_dump_json()


@pytest.mark.parametrize("hidden", [{"source": "SECRET"}, {"target": "SECRET"}, {"link": "SECRET"}])
async def test_the_links_emails_the_workspace_hands_its_reader_refuse_as_a_missing_link(
    hidden: dict[str, Any],
) -> None:
    """The workspace builds the same view from the link's event listing (`readerViewOf`) for an
    email not yet written as a Document. That listing carries all four ids, and gives none where
    the link or an end is above the reader."""
    reader, _ = await _world(**hidden)
    listing = LinkEventsService(reader._working_set, reader._analytics)
    with pytest.raises(LinkNotFoundError) as withheld:
        await listing.list("inv-1", LINK, ANALYST)
    reader, _ = await _world(link=None)
    listing = LinkEventsService(reader._working_set, reader._analytics)
    with pytest.raises(LinkNotFoundError) as missing:
        await listing.list("inv-1", LINK, ANALYST)
    assert str(withheld.value) == str(missing.value)
