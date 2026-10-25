"""Every delta is projected for its reader (ADR-124 decision 4, rules 3 and 7): a removal, a
resolution change and a link's replacement each name ids, and what a reader is sent of them is
decided by what that reader may read of the thing named, from a record the delta carries.

Each referent is shown red first: the removed hidden id, the reproject reason and keys, each row of
the replacement, and an old removal that has no record. The record travels on the stream and on
Pub/Sub (the stored forms, `DeltaRemove` and `DeltaReplaceEdge`); it never reaches a socket (the
sent forms, `DeltaRemoveSent` and `DeltaReplaceEdgeSent`).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError
from services.api.working_set.models import (
    DeltaAdd,
    DeltaRemove,
    DeltaRemoveSent,
    DeltaReplaceEdge,
    DeltaReplaceEdgeSent,
    DeltaReproject,
    DeltaSnapshot,
    RemovedElement,
    RemovedRecord,
    decode_delta,
)
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Handling, Principal, Subgraph

from ..corpus_counts import keys_at_any_depth
from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

CASE = "inv-1"


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


def _marking(edge_: Edge, source: str | None = None, target: str | None = None) -> RemovedElement:
    return RemovedElement(
        handling=edge_.handling,
        datasets=edge_.datasets,
        source=source or edge_.source,
        target=target or edge_.target,
    )


# --- DeltaRemove ---------------------------------------------------------------------------


async def test_removing_nodes_records_what_each_was() -> None:
    """Violation caught: a removal that names ids and nothing about them, so a later projection
    can only pass them all on or drop them all. The service reads each stored body before it
    removes it and the delta it returns, stores and publishes holds the record."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])

    delta = await _service(store).remove(CASE, ["pub", "sec", "never-stored"], SECRET_READER)

    assert isinstance(delta, DeltaRemove)
    assert delta.node_ids == ["pub", "sec"]  # names only what was removed (decision 6)
    assert delta.removed is not None
    assert {i: m.handling.classification for i, m in delta.removed.nodes.items()} == {
        "pub": "OFFICIAL",
        "sec": "SECRET",
    }
    assert (await store.deltas_after(CASE, 0)) == [delta]


def test_project_delta_drops_a_removed_id_the_record_marks_above_the_reader() -> None:
    """Violation caught (rule 3), against `project_delta` alone: a removal passed through as it was
    stored, so the SECRET node's id and the record itself went to an OFFICIAL reader's socket."""
    delta = DeltaRemove(
        seq=1,
        node_ids=["pub", "sec"],
        removed=RemovedRecord(  # type: ignore[call-arg]
            nodes={
                "pub": RemovedElement(handling=node("pub").handling),
                "sec": RemovedElement(handling=node("sec", "SECRET").handling),
            }
        ),
    )

    sent = _service(FakeWorkingSetStore()).project_delta(delta, OFFICIAL_READER)

    assert type(sent) is DeltaRemoveSent
    assert sent.node_ids == ["pub"]
    assert "sec" not in sent.model_dump_json() and "removed" not in sent.model_dump_json()


async def test_the_removals_record_is_built_from_the_counted_index_and_reads_no_body() -> None:
    """Violation caught (cost; the counted access index of ADR-124 Amendment 4): a record built by
    reading each removed node's body, a round trip and a decode for every id. The counted access
    index already holds each node's handling and datasets (its signature), read for all the ids in
    one lookup."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [node("pub"), _in(["fixture"], node("scoped")), node("sec", "SECRET")],  # type: ignore[list-item]
    )

    async def no_body_read(investigation_id: str, node_id: str) -> object:
        raise AssertionError(f"the record read the body of {node_id}")

    store.get_node = no_body_read  # type: ignore[method-assign]
    delta = await _service(store).remove(
        CASE, ["pub", "scoped", "sec", "never-stored"], SECRET_READER
    )

    assert delta.removed is not None
    assert {i: (m.handling.classification, m.datasets) for i, m in delta.removed.nodes.items()} == {
        "pub": ("OFFICIAL", []),
        "scoped": ("OFFICIAL", ["fixture"]),
        "sec": ("SECRET", []),
    }


async def test_a_node_rewritten_between_the_records_two_reads_is_still_in_the_record() -> None:
    """Violation caught: the record read the signature table and then the entries, so a node
    rewritten under a new signature between the two had an entry naming a signature the table it
    already held did not define, and was left out of the record (its removal then reached no one).
    Entries first: whatever an entry names, the table read after it defines."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("x")])
    service = _service(store)
    first_read_done = False
    real_counts, real_entries = store.access_counts, store.access_entries

    async def rewrite_after_the_first_read() -> None:
        nonlocal first_read_done
        if not first_read_done:
            first_read_done = True
            await store.add_nodes(CASE, [node("x", "SECRET")])  # a new signature, same node

    async def counts(investigation_id: str) -> object:
        result = await real_counts(investigation_id)
        await rewrite_after_the_first_read()
        return result

    async def entries(investigation_id: str, node_ids: object, edge_ids: object) -> object:
        result = await real_entries(investigation_id, node_ids, edge_ids)  # type: ignore[arg-type]
        await rewrite_after_the_first_read()
        return result

    store.access_counts = counts  # type: ignore[method-assign]
    store.access_entries = entries  # type: ignore[method-assign]

    record = await service._record_of_nodes(CASE, ["x"])

    assert "x" in record.nodes


async def _removed_hidden_node_projections() -> dict[str, DeltaRemoveSent]:
    """The one removal of a stored OFFICIAL and a stored SECRET node, as each path projects it for
    an OFFICIAL reader: directly, live, and as a reconnect's catch-up."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    delta = await service.remove(CASE, ["pub", "sec"], SECRET_READER)
    live = await service.project_live(CASE, delta, OFFICIAL_READER)
    caught_up = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=0)
    sent = {
        "project_delta": service.project_delta(delta, OFFICIAL_READER),
        "project_live": live,
        "sync": caught_up[0],
    }
    assert all(isinstance(d, DeltaRemoveSent) for d in sent.values())
    return sent  # type: ignore[return-value]


async def test_a_removed_hidden_id_never_reaches_an_uncleared_reader_by_any_path() -> None:
    """Violation caught (rule 3): `project_delta` passed a removal through unchanged, so a removed
    SECRET node's id went to every socket and into every catch-up. The record says the reader may
    not read it, so it is not sent, by each of the three paths."""
    for path, sent in (await _removed_hidden_node_projections()).items():
        assert sent.node_ids == ["pub"], path
        assert type(sent) is DeltaRemoveSent, path
        assert "sec" not in sent.model_dump_json(), path


async def test_a_removed_node_the_reader_may_read_is_sent_whole_to_a_cleared_reader() -> None:
    """The positive control: the same removal, for a reader who may read both ids."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    delta = await service.remove(CASE, ["pub", "sec"], SECRET_READER)

    sent = service.project_delta(delta, SECRET_READER)

    assert isinstance(sent, DeltaRemoveSent) and sent.node_ids == ["pub", "sec"]


async def test_the_record_is_never_sent() -> None:
    """Violation caught (ADR-124 decision 4): a projection that returns the stored delta, record
    and all. The sent form holds the key `removed` nowhere, for any reader, at any depth."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    delta = await service.remove(CASE, ["pub", "sec"], SECRET_READER)

    for reader in (OFFICIAL_READER, SECRET_READER):
        sent = service.project_delta(delta, reader)
        assert "removed" not in keys_at_any_depth(sent.model_dump(mode="json"))
        assert '"removed"' not in sent.model_dump_json()


async def test_an_id_the_store_never_held_is_sent_to_no_one() -> None:
    """A removed id with no record entry (it was not stored) cannot be judged and is not sent: the
    same as a hidden one, so the two read alike."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub")])
    service = _service(store)
    delta = await service.remove(CASE, ["pub", "ghost"], SECRET_READER)

    for reader in (OFFICIAL_READER, SECRET_READER):
        sent = service.project_delta(delta, reader)
        assert isinstance(sent, DeltaRemoveSent) and sent.node_ids == ["pub"]


async def test_a_removed_link_is_sent_only_to_a_reader_who_may_read_it_and_both_its_ends() -> None:
    """`edge_ids` takes a link off the canvas. A link the reader may read whose end they may not is
    not one they were ever sent, so its id is not sent either."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b"), node("s", "SECRET")])
    service = _service(store)
    readable = edge("ab", "a", "b")
    to_hidden_end = edge("as", "a", "s")
    secret_link = edge("ab2", "a", "b", "SECRET")
    delta = DeltaRemove(
        seq=1,
        edge_ids=["ab", "as", "ab2"],
        removed={  # type: ignore[arg-type]
            "edges": {
                "ab": _marking(readable),
                "as": _marking(to_hidden_end),
                "ab2": _marking(secret_link),
            }
        },
    )

    official = service.project_live(CASE, delta, OFFICIAL_READER)
    cleared = service.project_live(CASE, delta, SECRET_READER)

    official_sent, cleared_sent = await official, await cleared
    assert isinstance(official_sent, DeltaRemoveSent) and official_sent.edge_ids == ["ab"]
    assert isinstance(cleared_sent, DeltaRemoveSent)
    assert cleared_sent.edge_ids == ["ab", "as", "ab2"]


# --- an old removal without the record ---------------------------------------------------------


async def test_a_stored_removal_without_the_record_gives_a_reconnect_a_full_snapshot() -> None:
    """Violation caught: a removal stored before the record existed is passed on (its ids may be
    ones the reader may not read) or has its ids dropped (the reader's canvas then differs from a
    snapshot's). `deltas_after` answers `None`, so the reader is sent the whole view."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    await store.next_seq(CASE)
    await store.append_delta(CASE, DeltaRemove(seq=1, node_ids=["sec"]))
    await store.next_seq(CASE)
    service = _service(store)

    assert await store.deltas_after(CASE, 0) is None
    sent = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=0)

    assert len(sent) == 1 and isinstance(sent[0], DeltaSnapshot)
    assert {n.id for n in sent[0].nodes} == {"pub"}


async def test_a_stored_replacement_without_the_record_gives_a_reconnect_a_full_snapshot() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(CASE, [edge("new", "a", "b")])
    await store.next_seq(CASE)
    await store.append_delta(
        CASE, DeltaReplaceEdge(seq=1, old_edge_id="old", edge=edge("new", "a", "b"))
    )

    assert await store.deltas_after(CASE, 0) is None


async def test_the_fake_stream_round_trips_what_it_stores_as_the_real_one_does() -> None:
    """Violation caught: a fake that keeps the object it was given, so a sent form appended to the
    stream (which the real store would decode as a stored form with no record) stays a sent form
    and is replayed, while the real stream answers `None`."""
    store = FakeWorkingSetStore()
    await store.next_seq(CASE)
    await store.append_delta(CASE, DeltaRemoveSent(seq=1, node_ids=["sec"]))

    assert await store.deltas_after(CASE, 0) is None


async def test_a_removal_with_its_record_is_replayed_to_a_reconnect() -> None:
    """The control for the two above: with the record the stream answers as it always did."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    await service.remove(CASE, ["sec"], SECRET_READER)

    replayed = await store.deltas_after(CASE, 0)

    assert replayed is not None and len(replayed) == 1


# --- DeltaReproject ----------------------------------------------------------------------------


async def test_the_service_stores_a_fixed_reason_code_and_never_prose_that_names_ids() -> None:
    """Violation caught: `reason` was "manual link between {node_a} and {node_b}", which named ids
    to every reader. The delta the service stores now carries a code."""
    store = FakeWorkingSetStore()
    people = [node("n1"), node("n2")]
    service = WorkingSetService(FakeGraphPort(Subgraph(nodes=people, edges=[])), store, SCHEME)
    await store.add_nodes(CASE, people)
    outcome, _ = await service.manual_link(CASE, "n1", "n2", OFFICIAL_READER)

    assert outcome.delta.reason == "manual_resolution"
    stored = (await store.deltas_after(CASE, 0)) or []
    assert [d.reason for d in stored if isinstance(d, DeltaReproject)] == ["manual_resolution"]
    assert "n1" not in outcome.delta.reason and "n2" not in outcome.delta.reason


@pytest.mark.parametrize(
    ("stored_reason", "sent_reason"),
    [
        ("resolution_threshold", "resolution_threshold"),
        ("manual_resolution", "manual_resolution"),
        ("resolution threshold changed from 0.95 to 0.8", "resolution_threshold"),
        ("manual link between hidden-node and n2", "resolution_threshold"),
        ("", "resolution_threshold"),
    ],
)
async def test_a_reproject_is_sent_with_one_of_two_fixed_reason_codes(
    stored_reason: str, sent_reason: str
) -> None:
    """Violation caught (rule 3): `reason` passed through as stored, so an old entry's prose, which
    names ids, reached every socket. Any text other than the two codes is sent as the threshold."""
    store = FakeWorkingSetStore()
    service = _service(store)

    sent = service.project_delta(DeltaReproject(seq=1, reason=stored_reason), OFFICIAL_READER, {})

    assert isinstance(sent, DeltaReproject) and sent.reason == sent_reason


async def test_a_reprojects_cluster_keys_are_cut_to_nodes_the_reader_may_read() -> None:
    """Violation caught (rule 3): `affected_cluster_ids` passed through, so a node a reader may not
    read was named as a key. Only keys they may read are sent; a key the store does not hold cannot
    be judged and is not sent."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
    service = _service(store)
    delta = DeltaReproject(
        seq=1,
        reason="resolution_threshold",
        affected_cluster_ids={"pub": "c-pub", "sec": "c-sec", "ghost": "c-ghost"},
    )

    official = await service.project_live(CASE, delta, OFFICIAL_READER)
    cleared = await service.project_live(CASE, delta, SECRET_READER)

    assert isinstance(official, DeltaReproject) and official.affected_cluster_ids == {
        "pub": "c-pub"
    }
    assert isinstance(cleared, DeltaReproject)
    assert cleared.affected_cluster_ids == {"pub": "c-pub", "sec": "c-sec"}


# --- DeltaReplaceEdge: one row each ----------------------------------------------------------


async def _replace(
    *,
    old: Edge,
    new: Edge,
    old_ends: tuple[str, str] | None = None,
    stored: list[tuple[str, str]] | None = None,
) -> tuple[WorkingSetService, DeltaReplaceEdge]:
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            node(n, c)
            for n, c in (stored or [("a", "OFFICIAL"), ("b", "OFFICIAL"), ("s", "SECRET")])
        ],
    )
    ends = old_ends or (old.source, old.target)
    delta = DeltaReplaceEdge(
        seq=1,
        old_edge_id=old.id,
        edge=new,
        removed=_marking(old, *ends),
    )
    return _service(store), delta


async def _sent(service: WorkingSetService, delta: DeltaReplaceEdge, reader: Principal) -> object:
    return await service.project_live(CASE, delta, reader)


async def test_row_one_the_replace_when_the_reader_may_read_both_links_and_their_ends() -> None:
    service, delta = await _replace(old=edge("old", "a", "b"), new=edge("new", "a", "b"))

    sent = await _sent(service, delta, OFFICIAL_READER)

    assert type(sent) is DeltaReplaceEdgeSent
    assert sent.old_edge_id == "old" and sent.edge.id == "new"  # type: ignore[attr-defined]
    assert "removed" not in keys_at_any_depth(sent.model_dump(mode="json"))  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("old", "old_ends"),
    [
        (edge("old", "a", "b", "SECRET"), None),  # the old link's own marking is above them
        (edge("old", "a", "b"), ("a", "s")),  # the old link's end is
    ],
    ids=["old link above the reader", "old link's end above the reader"],
)
async def test_row_two_a_plain_add_of_the_new_link_when_the_old_one_is_not_theirs(
    old: Edge, old_ends: tuple[str, str] | None
) -> None:
    """Violation caught: the replace judged on the new link alone, so the old link's id reached a
    reader who never held it. They are sent the new link as an addition and nothing of the old."""
    service, delta = await _replace(old=old, new=edge("new", "a", "b"), old_ends=old_ends)

    sent = await _sent(service, delta, OFFICIAL_READER)

    assert type(sent) is DeltaAdd
    assert [e.id for e in sent.edges] == ["new"] and sent.nodes == []  # type: ignore[attr-defined]
    assert "old" not in sent.model_dump_json()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("new", "stored"),
    [
        (edge("new", "a", "b", "SECRET"), None),  # raised above the reader
        (edge("new", "a", "s"), None),  # the new link's end is
    ],
    ids=["new link above the reader", "new link's end above the reader"],
)
async def test_row_three_a_removal_of_the_old_link_when_the_new_one_is_not_theirs(
    new: Edge, stored: list[tuple[str, str]] | None
) -> None:
    """Violation caught: a replace whose new half the reader may not read was passed through, which
    sends the new link's content and ends, or dropped, which leaves the old link on their canvas.
    They are sent the old link's removal and nothing of the new."""
    service, delta = await _replace(old=edge("old", "a", "b"), new=new, stored=stored)

    sent = await _sent(service, delta, OFFICIAL_READER)

    assert type(sent) is DeltaRemoveSent
    assert sent.edge_ids == ["old"] and sent.node_ids == []  # type: ignore[attr-defined]
    assert "new" not in sent.model_dump_json()  # type: ignore[attr-defined]


async def test_row_four_nothing_when_the_reader_may_read_neither() -> None:
    service, delta = await _replace(
        old=edge("old", "a", "b", "SECRET"), new=edge("new", "a", "b", "SECRET")
    )

    sent = await _sent(service, delta, OFFICIAL_READER)

    assert type(sent) is DeltaRemoveSent
    assert sent.node_ids == [] and sent.edge_ids == []  # type: ignore[attr-defined]
    assert sent.seq == 1  # type: ignore[attr-defined]


async def test_a_cleared_reader_is_sent_the_replace_in_every_row() -> None:
    for old, new, ends in (
        (edge("old", "a", "b", "SECRET"), edge("new", "a", "b"), None),
        (edge("old", "a", "b"), edge("new", "a", "b", "SECRET"), None),
        (edge("old", "a", "b"), edge("new", "a", "s"), None),
        (edge("old", "a", "b", "SECRET"), edge("new", "a", "b", "SECRET"), ("a", "s")),
    ):
        service, delta = await _replace(old=old, new=new, old_ends=ends)
        sent = await _sent(service, delta, SECRET_READER)
        assert type(sent) is DeltaReplaceEdgeSent


async def test_replacing_a_link_records_what_the_old_one_was() -> None:
    """Violation caught: `replace_edge` took only the old link's id, so the delta could not say
    whether a reader may read the link it removes. It takes the old link and records its
    handling, datasets and ends."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    old = edge("old", "a", "b", "SECRET")
    await store.add_edges(CASE, [old])
    service = _service(store)

    delta = await service.replace_edge(CASE, old, edge("new", "a", "b"))

    assert delta.removed is not None
    assert delta.removed.handling == Handling(**old.handling.model_dump())
    assert (delta.removed.source, delta.removed.target) == ("a", "b")
    assert (await store.deltas_after(CASE, 0)) == [delta]


# --- a delta type nothing produces is not a delta type --------------------------------------


def test_the_projection_refuses_a_delta_it_has_no_rule_for() -> None:
    """Violation caught (rule 3): a fall-through that returned whatever it was given, so a delta of
    a type added later, naming ids, reached every socket unprojected. An unknown type raises."""

    class _Unprojected(BaseModel):
        seq: int = 1

    with pytest.raises(TypeError, match="_Unprojected"):
        _service(FakeWorkingSetStore()).project_delta(_Unprojected(), OFFICIAL_READER)  # type: ignore[arg-type]


def test_a_stored_update_delta_no_longer_decodes() -> None:
    """`DeltaUpdate` had no producer and named node ids with their properties; it left the delta
    protocol, so neither a stream entry nor a published message of that shape is a delta."""
    with pytest.raises(ValidationError):
        decode_delta({"seq": 1, "op": "update", "nodes": [{"id": "x", "properties": {}}]})


# --- the stored forms and the sent forms are different types ---------------------------------


def test_a_stored_form_is_not_a_sent_form_so_the_type_checker_keeps_them_apart() -> None:
    """Violation caught (ADR-124 decision 4): a stored form that is a subclass of its sent form, so
    a function typed to send one accepts the other and the record rides out under a parent's type.
    They are separate types; the stored one converts to the sent one explicitly."""
    assert not issubclass(DeltaRemove, DeltaRemoveSent)
    assert not issubclass(DeltaReplaceEdge, DeltaReplaceEdgeSent)


def test_a_stored_removal_converts_to_the_sent_form_without_its_record() -> None:
    stored = DeltaRemove(
        seq=3,
        node_ids=["a"],
        edge_ids=["e"],
        removed=RemovedRecord(nodes={"a": RemovedElement(handling=node("a").handling)}),
    )

    sent = stored.to_sent()

    assert type(sent) is DeltaRemoveSent
    assert (sent.seq, sent.node_ids, sent.edge_ids) == (3, ["a"], ["e"])
    assert "removed" not in sent.model_dump_json()


def test_a_stored_replacement_converts_to_the_sent_form_without_its_record() -> None:
    stored = DeltaReplaceEdge(
        seq=4,
        old_edge_id="old",
        edge=edge("new", "a", "b"),
        removed=_marking(edge("old", "a", "b")),
    )

    sent = stored.to_sent()

    assert type(sent) is DeltaReplaceEdgeSent
    assert (sent.seq, sent.old_edge_id, sent.edge.id) == (4, "old", "new")
    assert "removed" not in sent.model_dump_json()


# --- the datasets axis (ADR-099): a reader of a case reads only the case's datasets --------------

IN_FIXTURE = OFFICIAL_READER.model_copy(update={"datasets": ["fixture"]})
BOTH = ["fixture", "enron"]


def _in(datasets: list[str], element: object) -> object:
    return element.model_copy(update={"datasets": datasets})  # type: ignore[attr-defined]


async def test_a_removed_node_in_another_dataset_never_reaches_a_reader_of_the_case() -> None:
    """Violation caught (rule 3): a record judged on handling alone (`principal_may_view`), or one
    that dropped the datasets, so a case-scoped reader is sent the id of a node that is in another
    dataset (the first) or none of the case's own (the second)."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [_in(["fixture"], node("mine")), _in(["enron"], node("theirs")), _in(BOTH, node("shared"))],  # type: ignore[list-item]
    )
    service = _service(store)
    delta = await service.remove(CASE, ["mine", "theirs", "shared"], SECRET_READER)

    scoped = await service.project_live(CASE, delta, IN_FIXTURE)
    unscoped = await service.project_live(CASE, delta, OFFICIAL_READER)

    assert isinstance(scoped, DeltaRemoveSent) and scoped.node_ids == ["mine", "shared"]
    assert isinstance(unscoped, DeltaRemoveSent) and unscoped.node_ids == [
        "mine",
        "theirs",
        "shared",
    ]


async def test_a_removed_link_in_another_dataset_is_not_sent_to_a_reader_of_the_case() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_in(BOTH, node("a")), _in(BOTH, node("b"))])  # type: ignore[list-item]
    mine = _in(["fixture"], edge("mine", "a", "b"))
    theirs = _in(["enron"], edge("theirs", "a", "b"))
    delta = DeltaRemove(
        seq=1,
        edge_ids=["mine", "theirs"],
        removed=RemovedRecord(
            edges={"mine": _marking(mine), "theirs": _marking(theirs)}  # type: ignore[arg-type]
        ),
    )

    scoped = await _service(store).project_live(CASE, delta, IN_FIXTURE)

    assert isinstance(scoped, DeltaRemoveSent) and scoped.edge_ids == ["mine"]


@pytest.mark.parametrize(
    ("old", "new", "expect"),
    [
        (["fixture"], ["fixture"], DeltaReplaceEdgeSent),
        (["enron"], ["fixture"], DeltaAdd),  # the old link is in another dataset
        (["fixture"], ["enron"], DeltaRemoveSent),  # the new one is
        (["enron"], ["enron"], DeltaRemoveSent),  # neither: nothing, an empty removal
    ],
    ids=["replace", "add of the new", "removal of the old", "nothing"],
)
async def test_each_replacement_row_for_a_reader_scoped_to_the_cases_datasets(
    old: list[str], new: list[str], expect: type
) -> None:
    """Violation caught (rule 3): the rows decided on handling alone, so a link in another dataset
    is sent (or its absence is taken for the reader's own) as though it were the case's."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_in(BOTH, node("a")), _in(BOTH, node("b"))])  # type: ignore[list-item]
    old_link = _in(old, edge("old", "a", "b"))
    delta = DeltaReplaceEdge(
        seq=1,
        old_edge_id="old",
        edge=_in(new, edge("new", "a", "b")),  # type: ignore[arg-type]
        removed=_marking(old_link),  # type: ignore[arg-type]
    )

    sent = await _service(store).project_live(CASE, delta, IN_FIXTURE)

    assert type(sent) is expect
    if expect is DeltaRemoveSent and old == ["enron"]:
        assert sent.edge_ids == [] and sent.node_ids == []  # type: ignore[attr-defined]


async def test_an_end_in_another_dataset_stops_a_replacement_reaching_a_reader_of_the_case() -> (
    None
):
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [_in(BOTH, node("a")), _in(["enron"], node("far"))],  # type: ignore[list-item]
    )
    link = _in(BOTH, edge("new", "a", "far"))
    delta = DeltaReplaceEdge(
        seq=1,
        old_edge_id="old",
        edge=link,  # type: ignore[arg-type]
        removed=_marking(_in(BOTH, edge("old", "a", "far"))),  # type: ignore[arg-type]
    )

    sent = await _service(store).project_live(CASE, delta, IN_FIXTURE)

    assert type(sent) is DeltaRemoveSent and sent.edge_ids == [] and sent.node_ids == []


async def test_a_reprojects_keys_in_another_dataset_are_not_sent_to_a_reader_of_the_case() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [_in(["fixture"], node("mine")), _in(["enron"], node("theirs"))],  # type: ignore[list-item]
    )
    delta = DeltaReproject(
        seq=1, reason="resolution_threshold", affected_cluster_ids={"mine": "c1", "theirs": "c2"}
    )

    sent = await _service(store).project_live(CASE, delta, IN_FIXTURE)

    assert isinstance(sent, DeltaReproject) and sent.affected_cluster_ids == {"mine": "c1"}


# --- a picture's replacement, for a reader scoped to the case --------------------------------


async def test_a_picture_replacement_is_stamped_with_the_cases_dataset_for_its_readers() -> None:
    """Violation caught (rule 3 and ADR-099): the picture path builds the new `DEPICTS` link with no
    datasets (`entity_pictures._edge_from`), so the copy in the working set belongs to none and a
    reader scoped to the case is sent the old link's removal and never the new link, which a
    snapshot then also leaves out. `replace_edge` stamps it as `add_written` does."""
    from services.api.dataset_scope import set_case_datasets

    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_in(["fixture"], node("doc")), _in(["fixture"], node("car"))])  # type: ignore[list-item]
    old = _in(["fixture"], edge("old-picture", "doc", "car"))
    await store.add_edges(CASE, [old])  # type: ignore[list-item]
    service = _service(store)
    set_case_datasets(["fixture"])
    try:
        delta = await service.replace_edge(CASE, old, edge("new-picture", "doc", "car"))  # type: ignore[arg-type]
    finally:
        set_case_datasets(None)

    assert delta.edge.datasets == ["fixture"]
    sent = await service.project_live(CASE, delta, IN_FIXTURE)
    assert type(sent) is DeltaReplaceEdgeSent and sent.edge.id == "new-picture"
    snapshot = await service.sync(CASE, IN_FIXTURE, last_acknowledged_seq=None)
    assert [e.id for e in snapshot[0].edges] == ["new-picture"]  # type: ignore[union-attr]


async def test_a_replacements_record_is_taken_from_the_working_sets_copy_of_the_old_link() -> None:
    """Violation caught: the record built from the old link as the caller held it (the Vault's
    copy, which the picture path reads by an expansion), whose datasets and marking can differ from
    the copy the canvas is drawn from. The working set's stored copy is what the readers had."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_in(["fixture"], node("a")), _in(["fixture"], node("b"))])  # type: ignore[list-item]
    stored = _in(["fixture"], edge("old", "a", "b", "SECRET"))
    await store.add_edges(CASE, [stored])  # type: ignore[list-item]
    held_by_the_caller = edge("old", "a", "b")  # no datasets, and a lower marking
    service = _service(store)

    delta = await service.replace_edge(CASE, held_by_the_caller, edge("new", "a", "b"))

    assert delta.removed is not None
    assert delta.removed.datasets == ["fixture"]
    assert delta.removed.handling.classification == "SECRET"
