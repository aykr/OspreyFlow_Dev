"""ADR-102 Amendment 3, rules 3 and 7: what a user-facing write puts on the canvas is the link the
store made, under the id the store gave it, and the id it sends reveals nothing.

A link write whose id a link of another audience already holds is a link of its own under a new id,
and `upsert_edges` returns that id (`graph_arcadedb/adapter.py`). Two things follow for a caller:

- **It builds its working-set edges and delta from the ids returned**, never the ones it sent. A
  caller that kept the sent id would name the other audience's link on the canvas, and the link notes
  opened on it would show that audience's notes (`test_the_delta_carries_the_ids_the_store_returned`).
- **It does not send an id a stranger could derive.** `{document}:held-by:{holder}` and
  `{document}:mentions:{end}` let a caller who knows the scheme learn, from a ULID coming back in
  their place, that another audience's link joins those ends. Both paths send `new_edge_id()`
  (`test_the_ids_sent_are_not_derivable`); a re-run within one audience still merges by pair in the
  store.

The graph fake answers as the adapter now does: it hands back an id of its own for every link it is
given, as it would for one whose id another audience's link holds."""

from __future__ import annotations

from collections.abc import Sequence

from services.api.email_extraction import email_document_id

from schemas.domain import EdgeWrite, TxId

from .test_document_content import OFFICIAL
from .test_document_content import _service as _content_service
from .test_email_extraction import ANALYST, WritingGraph, _build as _build_email


class RenamingGraph(WritingGraph):
    """`WritingGraph`, answering every link write with an id of the store's own (`stored-n`), as the
    adapter does for a link whose id another audience's link holds. The links it commits are under
    those ids."""

    def __init__(self) -> None:
        super().__init__()
        self._counter = 0
        self.sent: list[str] = []

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[str]:
        self.sent.extend(e.id for e in edges)
        stored: list[EdgeWrite] = []
        ids: list[str] = []
        for e in edges:
            self._counter += 1
            ids.append(f"stored-{self._counter}")
            stored.append(e.model_copy(update={"id": ids[-1]}))
        await super().upsert_edges(stored, tx)
        return ids


def _is_a_ulid(edge_id: str) -> bool:
    return len(edge_id) == 26 and edge_id.isalnum() and edge_id.upper() == edge_id


async def test_the_delta_carries_the_ids_the_store_returned_for_an_upload() -> None:
    service, _, _, _, graph, _ = await _content_service()
    graph.__class__ = RenamingGraph  # the service's own graph, now answering as the adapter does
    graph._counter, graph.sent = 0, []
    result = await service.upload(
        "inv-1", ANALYST, name="note.txt", data=b"Gate 3, 7am.", holder_id="phone", handling=OFFICIAL
    )
    assert [e.id for e in result.delta.edges] == ["stored-1"]
    (committed,) = [e for e in graph.committed_edges if e.type == "HOLDS"]
    assert committed.id == "stored-1"


async def test_the_delta_carries_the_ids_the_store_returned_for_an_email_extraction() -> None:
    service, graph, _, _, _ = await _build_email()
    graph.__class__ = RenamingGraph
    graph._counter, graph.sent = 0, []
    result = await service.extract("inv-1", "e1", "ev-1", ANALYST)
    assert sorted(e.id for e in result.delta.edges) == ["stored-1", "stored-2"]


async def test_the_delta_carries_the_ids_the_store_returned_for_emails_shown_as_documents() -> None:
    service, graph, _, _, _ = await _build_email()
    graph.__class__ = RenamingGraph
    graph._counter, graph.sent = 0, []
    result = await service.show_as_documents("inv-1", "e1", ANALYST, window=None)
    assert result.written >= 1
    assert all(e.id.startswith("stored-") for e in result.delta.edges)
    assert len(result.delta.edges) == 2 * result.written


async def test_the_ids_sent_are_not_derivable() -> None:
    """Neither path sends `{document}:held-by:{holder}` or `{document}:mentions:{end}`: a caller who
    knew the scheme would otherwise learn, from a different id coming back, that another audience's
    link joins those ends. What goes out is a fresh id, whether or not such a link exists."""
    service, _, _, _, graph, _ = await _content_service()
    graph.__class__ = RenamingGraph
    graph._counter, graph.sent = 0, []
    result = await service.upload(
        "inv-1", ANALYST, name="note.txt", data=b"Gate 3, 7am.", holder_id="phone", handling=OFFICIAL
    )
    (sent,) = graph.sent
    assert _is_a_ulid(sent) and "held-by" not in sent and result.document_id not in sent

    email, egraph, _, _, _ = await _build_email()
    egraph.__class__ = RenamingGraph
    egraph._counter, egraph.sent = 0, []
    await email.extract("inv-1", "e1", "ev-1", ANALYST)
    document = email_document_id("ev-1")
    assert len(egraph.sent) == 2
    assert all(_is_a_ulid(i) and "mentions" not in i and document not in i for i in egraph.sent)


async def test_the_response_is_the_same_shape_whether_or_not_another_audiences_link_joins_the_ends() -> None:
    """The edge ids in a response are fresh ids either way, so the response says nothing about a
    link the caller cannot read."""

    async def edge_ids(held_elsewhere: bool) -> list[str]:
        service, _, _, _, graph, _ = await _content_service()
        graph.__class__ = RenamingGraph if held_elsewhere else type(graph)
        graph._counter, graph.sent = 0, []
        result = await service.upload(
            "inv-1", ANALYST, name="note.txt", data=b"Gate 3, 7am.", holder_id="phone", handling=OFFICIAL
        )
        return [e.id for e in result.delta.edges]

    plain = await edge_ids(False)
    renamed = await edge_ids(True)
    assert len(plain) == len(renamed) == 1
    assert _is_a_ulid(plain[0])
    assert "held-by" not in plain[0] and "held-by" not in renamed[0]



async def test_an_accepted_finding_is_put_on_the_canvas_under_the_stores_link_id() -> None:
    """Accepting a finding writes a `MENTIONED_IN` link too; its delta names the link the store
    holds, as the writes above do."""
    service, _, _, _, graph, _ = await _content_service()
    graph.__class__ = RenamingGraph
    graph._counter, graph.sent = 0, []
    found = await service.extract("inv-1", "image-1", ANALYST)
    accepted = await service.accept("inv-1", "image-1", found.candidates[0].id, ANALYST)
    assert [e.id for e in accepted.delta.edges] == ["stored-1"]

    email, egraph, _, candidates, _ = await _build_email()
    egraph.__class__ = RenamingGraph
    egraph._counter, egraph.sent = 0, []
    extracted = await email.extract("inv-1", "e1", "ev-1", ANALYST)
    (candidate,) = extracted.candidates
    accepted_email = await email.accept("inv-1", "e1", "ev-1", candidate.id, ANALYST)
    assert [e.id for e in accepted_email.delta.edges] == ["stored-3"]
