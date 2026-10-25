"""The working set's access index (ADR-124 decision 2, Amendment 4): counts kept beside the bodies,
and the reader's figures computed from them.

The caps and previews count the reader's projected view. Reading every body for it cost 3.2 s of a
3.4 s preview at 50,000 nodes and 100,000 links; loading an entry per element still cost 1.1 s at
250,000 links. Nothing they need is the whole set: every use is a count or the membership of a few
named ids. The store keeps, in the transaction of each write, how many nodes carry each signature,
how many links carry each (link, source end, target end) triple (an end that is not stored being
`absent`), an entry per element and an adjacency; the service sums the counts over the signatures
the reader may read and looks up only the ids a request would add.

The cases and what each catches:

- consistency: after any run of adds, replacements, removes and clears, every structure equals what
  the bodies say (`test_every_structure_equals_what_the_bodies_say_after_any_run_of_operations`; the
  same against Valkey, running the real scripts, in `../test_valkey_store.py`);
- the triples: a node's removal, its re-add with another signature and a link's replacement each
  move the right counts (`test_a_node_removal_...`, `test_a_signature_change_...`,
  `test_a_replaced_link_...`), and `absent` is never readable;
- equivalence: the reader's counts and the membership of any id equal what `_project` gives over the
  bodies, for six readers, after every one of forty runs of thirty random operations;
- the readable-signature cache: keyed by case, epoch, signatures version and access class, so that
  a signature first stored, a case that starts again and a reader of another class are each a new
  key (the last a rule 3 leak if it were not);
- restore: the reconcile keeps the index consistent.
"""

from __future__ import annotations

import random

import pytest
from services.api.cache import principal_class
from services.api.working_set import service as service_module
from services.api.working_set.access_index import (
    ABSENT,
    IndexState,
    adjacency_member,
    adjacency_prefix,
    build_counted_index,
    decode_edge_entry,
    decode_signature,
    encode_edge_entry,
    encode_signature,
    signature_id,
    signature_of,
    triple_key,
)
from services.api.working_set.models import LimitExceededError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Node, Principal, Subgraph

from .access_index_ops import (
    DATASET_SETS,
    EDGE_IDS,
    NODE_IDS,
    apply_random_operation,
    assert_index_matches_bodies,
    random_edge,
    random_node,
)
from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

CASE = "case-1"


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


# --- consistency -------------------------------------------------------------------------------


async def test_every_structure_equals_what_the_bodies_say_after_any_run_of_operations() -> None:
    """Violation caught: an operation that changes the bodies and not the counts (a remove that
    leaves its count, a replacement that keeps the old signature's, a node's removal that does not
    move its links' triples, a clear that keeps the index). Sixty seeded runs of forty operations;
    every structure is checked after every one."""
    for seed in range(60):
        rng = random.Random(seed)
        store = FakeWorkingSetStore()
        for step in range(40):
            kind = await apply_random_operation(store, CASE, rng)
            await assert_index_matches_bodies(store, CASE, f"seed {seed} step {step} {kind}")


async def test_each_operation_is_covered_by_the_runs_above() -> None:
    """Violation caught: the generator never produces one kind of operation, so the consistency
    runs prove nothing about it."""
    seen: set[str] = set()
    for seed in range(60):
        rng = random.Random(seed)
        store = FakeWorkingSetStore()
        for _ in range(40):
            seen.add(await apply_random_operation(store, CASE, rng))
    assert seen == {"add_nodes", "add_edges", "remove_nodes", "remove_edges", "clear"}


# --- the triples -------------------------------------------------------------------------------


def _sig(held: Node | Edge) -> str:
    return signature_id(signature_of(held.handling, held.datasets))


async def test_a_node_removal_moves_its_links_triples_to_absent_and_adjacency_stays() -> None:
    """Violation caught: a removal that leaves the links counted under the removed node's
    signature, so a reader who may read it is counted a link to a node that is gone (and a reader
    who may not, one less than the bodies say). The links stay stored, each end `absent`, and the
    adjacency stays so that the node's return moves them back."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b"), node("s", "SECRET")])
    await store.add_edges(CASE, [edge("ab", "a", "b"), edge("as", "a", "s")])
    official, secret = _sig(node("a")), _sig(node("s", "SECRET"))
    before = (await store.counted_index(CASE)).edge_counts
    assert before == {(official, official, official): 1, (official, official, secret): 1}

    await store.remove_nodes(CASE, ["s"])

    index = await store.counted_index(CASE)
    assert index.edge_counts == {(official, official, official): 1, (official, official, ABSENT): 1}
    assert ("s", "as") in index.adjacency, "kept whether or not the node is stored"
    await assert_index_matches_bodies(store, CASE, "after the removal")

    await store.add_nodes(CASE, [node("s", "SECRET")])  # the node returns: the links move back
    assert (await store.counted_index(CASE)).edge_counts == before
    await assert_index_matches_bodies(store, CASE, "after the return")


async def test_a_signature_change_of_a_node_with_links_moves_each_of_them() -> None:
    """Violation caught: a re-add with another signature that updates the node's own count and not
    its links' triples, which leaves a link counted as to a readable end when the end was raised
    above the reader. The node here has a link out, a link in and a link to itself."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(
        CASE, [edge("a-b", "a", "b"), edge("b-a", "b", "a"), edge("a-a", "a", "a")]
    )
    official, secret = _sig(node("a")), _sig(node("a", "SECRET"))
    assert (await store.counted_index(CASE)).edge_counts == {(official, official, official): 3}

    await store.add_nodes(CASE, [node("a", "SECRET")])  # raised

    index = await store.counted_index(CASE)
    assert index.node_counts == {official: 1, secret: 1}
    assert index.edge_counts == {
        (official, secret, official): 1,
        (official, official, secret): 1,
        (official, secret, secret): 1,
    }
    await assert_index_matches_bodies(store, CASE, "after the raise")

    await store.add_nodes(CASE, [node("a")])  # lowered again
    assert (await store.counted_index(CASE)).edge_counts == {(official, official, official): 3}


async def test_a_replaced_link_counts_out_its_old_triple() -> None:
    """Violation caught: a replacement that adds the new triple and keeps the old, so a link that
    was raised stays counted at its old signature too (two links where the bodies hold one)."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(CASE, [edge("ab", "a", "b")])
    official, secret = _sig(node("a")), _sig(node("a", "SECRET"))

    await store.add_edges(CASE, [edge("ab", "a", "b", "SECRET")])  # the same link, raised

    index = await store.counted_index(CASE)
    assert index.edge_counts == {(secret, official, official): 1}
    assert sum(index.edge_counts.values()) == 1
    await assert_index_matches_bodies(store, CASE, "after the replacement")

    await store.add_edges(CASE, [edge("ab", "b", "a")])  # and again, with its ends turned round
    assert (await store.counted_index(CASE)).adjacency == {("a", "ab"), ("b", "ab")}
    await assert_index_matches_bodies(store, CASE, "after the turn")


def test_absent_is_never_a_signature_key_and_never_readable() -> None:
    """Violation caught: `absent` treated as readable, which counts a link to a node that is not
    stored as in every reader's view. A link's triple is judged readable only when all three keys
    are in the reader's readable set, and `absent` is not a key the store can give a signature."""
    state = IndexState()
    signature = signature_of(node("a").handling, [])
    state.set_edge("e", signature_id(signature), signature, "a", "b")  # neither end stored
    assert list(state.index.edge_counts) == [(signature_id(signature), ABSENT, ABSENT)]
    assert ABSENT not in state.index.signatures
    assert ABSENT not in {signature_id(signature)}


async def test_an_unstored_ends_link_is_in_no_readers_view() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a")])
    await store.add_edges(CASE, [edge("to-nowhere", "a", "never-stored")])
    service = _service(store)

    for reader in (OFFICIAL_READER, SECRET_READER):
        counts = await service._reader_counts(CASE, reader)
        assert (counts.nodes, counts.edges) == (1, 0)


# --- encodings ---------------------------------------------------------------------------------


def test_an_edge_entry_holds_any_id_whatever_characters_it_has() -> None:
    """Violation caught: an entry joined with a separator, which an id containing it splits wrongly.
    Each part is led by its length, so no character is reserved."""
    awkward = [
        "a\x1fb",
        'quo"te',
        "com,ma",
        "new\nline",
        "back\\slash",
        "[bracket]",
        "ünï",
        "1:2",
        "",
    ]
    for source in awkward:
        for target in awkward:
            blob = encode_edge_entry("12", source, target)
            assert decode_edge_entry(blob) == ("12", source, target)


def test_a_length_prefix_counts_bytes_because_the_scripts_do() -> None:
    """Violation caught: a prefix counting characters, which a script (whose `#` counts bytes)
    reads as a different length for any id with a non-ASCII character: the link's entry then
    parses to the wrong ends and the adjacency to the wrong node. Found by running the scripts."""
    assert adjacency_prefix("ünï") == "5:ünï".encode()
    assert encode_edge_entry("1", "ünï", "ß") == "1:15:ünïß".encode()
    assert decode_edge_entry("1:15:ünïß".encode()) == ("1", "ünï", "ß")


def test_the_adjacency_prefix_of_one_node_is_never_the_prefix_of_another_nodes_members() -> None:
    """Violation caught: a range over one node's members that returns another's (a node whose id
    is the start of another's)."""
    nodes = ["a", "ab", "a:b", "1:a", "a\x00", "ü", "", "10:aaaaaaaaaa", "aaaaaaaaaa"]
    for owner in nodes:
        for other in nodes:
            if other != owner:
                assert not adjacency_member(other, "e1").startswith(adjacency_prefix(owner))


def test_a_signature_id_is_the_full_sha256_digest_and_signatures_do_not_share_one() -> None:
    first, second = _sig(node("a")), _sig(node("b", "SECRET"))
    assert len(first) == 64 and int(first, 16) >= 0
    assert first != second
    assert _sig(node("other")) == first  # the same signature, the same id


def test_a_signature_round_trips_and_the_triple_key_splits_back() -> None:
    signature = signature_of(node("a").handling, ["enron", "fixture"])
    assert decode_signature(encode_signature(signature)) == signature
    assert triple_key("1", "2", ABSENT).split(",") == ["1", "2", ABSENT]


# --- the reader's counts equal the projection --------------------------------------------------

IN_UNIT_R = Principal(
    id="r", clearance="OFFICIAL", org_unit="unit-2", receivable_handling_codes=["C"]
)
READERS = {
    "official": OFFICIAL_READER,
    "secret": SECRET_READER,
    "unit restricted": IN_UNIT_R,
    "enron": OFFICIAL_READER.model_copy(update={"datasets": ["enron"]}),
    "enron and fixture": SECRET_READER.model_copy(update={"datasets": ["enron", "fixture"]}),
    "nothing": SECRET_READER.model_copy(update={"datasets": []}),
}


def _world() -> tuple[list[Node], list[Edge]]:
    nodes = [
        node("a"),
        node("b"),
        node("hidden", "SECRET"),
        node("enron-only").model_copy(update={"datasets": ["enron"]}),
        node("fixture-only").model_copy(update={"datasets": ["fixture"]}),
        node("restricted").model_copy(
            update={
                "handling": node("x").handling.model_copy(
                    update={"handling_code": "C", "owning_unit": "unit-2", "originator": "unit-2"}
                )
            }
        ),
    ]
    edges = [
        edge("a-b", "a", "b"),
        edge("a-hidden", "a", "hidden", "OFFICIAL"),  # readable link to a hidden node
        edge("a-b-secret", "a", "b", "SECRET"),  # hidden link between readable nodes
        edge("a-enron", "a", "enron-only"),
        edge("b-fixture", "b", "fixture-only"),
        edge("a-restricted", "a", "restricted"),
        edge("a-absent", "a", "never-stored"),  # an end that is not in the case
        edge("hidden-hidden", "hidden", "hidden", "SECRET"),
    ]
    return nodes, edges


async def _assert_counts_are_the_projections(
    service: WorkingSetService,
    store: FakeWorkingSetStore,
    reader_name: str,
    reader: Principal,
    where: object,
) -> None:
    """The reader's counts, and whether each id ever generated is in their view, equal what
    `_project` gives over the bodies."""
    nodes = list((await store.source_fidelity_nodes(CASE)).values())
    edges = list((await store.source_fidelity_edges(CASE)).values())
    projected_nodes, projected_edges, _ = service._project(nodes, edges, reader)
    counts = await service._reader_counts(CASE, reader)
    assert counts.nodes == len(projected_nodes), (where, reader_name)
    assert counts.edges == len(projected_edges), (where, reader_name)
    entries = await store.access_entries(CASE, [*NODE_IDS, "gone"], [*EDGE_IDS, "unknown"])
    visible_nodes, visible_edges = counts.visibly_stored(entries)
    assert visible_nodes == {n.id for n in projected_nodes}, (where, reader_name)
    assert visible_edges == {e.id for e in projected_edges}, (where, reader_name)


@pytest.mark.parametrize("reader", READERS)
async def test_the_readers_counts_and_membership_are_the_projections(reader: str) -> None:
    nodes, edges = _world()
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, nodes)
    await store.add_edges(CASE, edges)
    service = _service(store)
    principal = READERS[reader]

    counts = await service._reader_counts(CASE, principal)

    projected_nodes, projected_edges, _ = service._project(nodes, edges, principal)
    assert counts.nodes == len(projected_nodes)
    assert counts.edges == len(projected_edges)
    entries = await store.access_entries(
        CASE, [n.id for n in nodes] + ["gone"], [e.id for e in edges] + ["unknown"]
    )
    visible_nodes, visible_edges = counts.visibly_stored(entries)
    assert visible_nodes == {n.id for n in projected_nodes}
    assert visible_edges == {e.id for e in projected_edges}
    assert await counts.visible_node_ids() == {n.id for n in projected_nodes}


async def test_the_readers_figures_are_not_empty_for_every_reader_and_differ_between_them() -> None:
    """Violation caught: equivalence passing because every reader's view is empty, or the same."""
    nodes, edges = _world()
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, nodes)
    await store.add_edges(CASE, edges)
    service = _service(store)

    figures = {}
    for name, principal in READERS.items():
        counts = await service._reader_counts(CASE, principal)
        figures[name] = (counts.nodes, counts.edges)

    assert figures["official"][0] > 0 and figures["secret"][0] > 0
    assert figures["nothing"] == (0, 0)
    assert figures["secret"] != figures["official"] and figures["enron"] != figures["official"]
    # A readable link to a hidden node is in the SECRET reader's view and not in the OFFICIAL's.
    assert figures["secret"][1] > figures["official"][1]


async def test_after_every_random_operation_the_counts_are_the_projections_for_each_reader() -> (
    None
):
    """The core property (Amendment 4): forty seeded runs of thirty random operations, among them
    removals that leave links dangling, re-adds, signature changes of nodes with links, replaced
    links and clears. After each, for each of six readers, the counts and the membership of every
    id the generator uses equal what `_project` gives over the bodies; readable signatures are
    cached throughout, so a key that does not move with a change is a failure here too."""
    for seed in range(40):
        rng = random.Random(seed)
        store = FakeWorkingSetStore()
        service = _service(store)
        for step in range(30):
            kind = await apply_random_operation(store, CASE, rng)
            for name, reader in READERS.items():
                await _assert_counts_are_the_projections(
                    service, store, name, reader, (seed, step, kind)
                )


# --- a new node completes the links stored at it ------------------------------------------------


async def _hub_case(readable_links: int = 3) -> tuple[FakeWorkingSetStore, Node]:
    """A hub with `readable_links` readable links from readable spokes, one link to a node above
    the reader, and the hub then removed: its links stay stored with `absent` for that end."""
    store = FakeWorkingSetStore()
    hub = node("hub")
    spokes = [node(f"spoke-{i}") for i in range(readable_links)]
    await store.add_nodes(CASE, [hub, *spokes, node("secret", "SECRET")])
    await store.add_edges(
        CASE,
        [edge(f"link-{i}", f"spoke-{i}", "hub") for i in range(readable_links)]
        + [edge("to-secret", "hub", "secret")],
    )
    await store.remove_nodes(CASE, ["hub"])
    return store, hub


async def test_a_new_node_that_completes_stored_links_adds_them_to_the_preview_and_the_cap() -> (
    None
):
    """Violation caught: figures that count only what a request names. The request names the hub
    (a node the store no longer holds) and no link; its readable links are stored, each with the
    hub `absent`, and the write completes them, so the reader's view after it is larger than the
    preview said. The preview's and the cap's figures must equal the projection after the write.
    The link to a node above the reader completes too, and is in nobody's view but theirs."""
    store, hub = await _hub_case()
    truth_store, _ = await _hub_case()
    graph = FakeGraphPort(Subgraph(nodes=[hub], edges=[]))
    from schemas.domain import ExpandRequest

    request = ExpandRequest(node_ids=["hub"], depth=1)
    await WorkingSetService(graph, truth_store, SCHEME).expand(CASE, request, OFFICIAL_READER)
    nodes = list((await truth_store.source_fidelity_nodes(CASE)).values())
    edges = list((await truth_store.source_fidelity_edges(CASE)).values())
    after_nodes, after_edges, _ = _service(truth_store)._project(nodes, edges, OFFICIAL_READER)
    assert len(after_edges) == 3, "the three readable links are in the view once the hub is back"

    service = WorkingSetService(graph, store, SCHEME)
    preview = await service.expand_preview(CASE, request, OFFICIAL_READER)

    assert preview.candidate_node_count == len(after_nodes)
    assert preview.candidate_edge_count == len(after_edges)
    # And the cap: set just below, the refusal's figure is the view after the write.
    saved = service_module.MAX_EDGES
    service_module.MAX_EDGES = len(after_edges) - 1
    try:
        again = await service.expand_preview(CASE, request, OFFICIAL_READER)
        assert again.would_breach is not None and again.would_breach.would_be == len(after_edges)
        with pytest.raises(LimitExceededError) as refused:
            await service.expand(CASE, request, OFFICIAL_READER)
        assert refused.value.detail.would_be == len(after_edges)
        with pytest.raises(LimitExceededError) as roomed:
            await service.ensure_room(CASE, ["hub"], [], OFFICIAL_READER)
        assert roomed.value.detail.would_be == len(after_edges)
    finally:
        service_module.MAX_EDGES = saved


async def test_a_link_between_two_new_nodes_is_counted_once() -> None:
    """Violation caught: a link completed from both of its ends counted twice."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(CASE, [edge("ab", "a", "b"), edge("ba", "b", "a")])
    await store.remove_nodes(CASE, ["a", "b"])  # both ends gone, both links dangle
    graph = FakeGraphPort(Subgraph(nodes=[node("a"), node("b")], edges=[]))
    from schemas.domain import ExpandRequest

    preview = await WorkingSetService(graph, store, SCHEME).expand_preview(
        CASE, ExpandRequest(node_ids=["a"], depth=1), OFFICIAL_READER
    )

    assert (preview.candidate_node_count, preview.candidate_edge_count) == (2, 2)


async def test_a_signature_no_node_or_link_carries_any_more_is_never_judged() -> None:
    """Violation caught: the readable set worked out over the whole signature table, which keeps a
    signature for as long as the case lives. One whose handling code the scheme no longer defines
    raises when judged; nothing carries it, so nothing should judge it."""
    store = FakeWorkingSetStore()
    stale = node("stale").model_copy(
        update={"handling": node("x").handling.model_copy(update={"handling_code": "REMOVED"})}
    )
    await store.add_nodes(CASE, [node("a"), stale])
    await store.remove_nodes(CASE, ["stale"])  # the signature stays in the table, counted at none
    assert len((await store.access_counts(CASE)).signatures) == 2

    counts = await _service(store)._reader_counts(CASE, OFFICIAL_READER)

    assert (counts.nodes, counts.edges) == (1, 0)


# --- the request's ids -------------------------------------------------------------------------


async def test_what_a_request_adds_is_what_is_not_already_in_the_readers_view() -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("a"), node("s", "SECRET")])
    await store.add_edges(CASE, [edge("as", "a", "s")])
    service = _service(store)
    view = await service._reader_counts(CASE, OFFICIAL_READER)

    new_nodes, new_edges, entries = await view.would_add(["a", "s", "z", "a"], ["as", "e-new"])

    # `a` is in the view; `s` is stored but above the reader, so it counts as new to them (the
    # same as a node that is not stored); `z` is new; `a` twice is once.
    assert new_nodes == 2
    # `as` is stored but not in their view (its end is above them); `e-new` is not stored.
    assert new_edges == 2
    assert set(entries.nodes) == {"a", "s"} and set(entries.edges) == {"as"}


async def test_a_requests_node_stored_but_hidden_is_the_same_to_the_reader_as_an_unstored_one() -> (
    None
):
    """Violation caught (rule 3): a figure that differs for an id the store holds above the reader
    and an id it never held, which a request naming guessed ids could read as membership."""
    with_hidden = FakeWorkingSetStore()
    await with_hidden.add_nodes(CASE, [node("a"), node("guess", "SECRET")])
    without = FakeWorkingSetStore()
    await without.add_nodes(CASE, [node("a")])

    figures = []
    for store in (with_hidden, without):
        view = await _service(store)._reader_counts(CASE, OFFICIAL_READER)
        new_nodes, new_edges, _ = await view.would_add(["guess"], [])
        figures.append((view.nodes, view.edges, new_nodes, new_edges))

    assert figures[0] == figures[1]


# --- the readable-signature cache --------------------------------------------------------------


class _CountingStore(FakeWorkingSetStore):
    """Counts the reads of the counts, to see the service's own work."""

    def __init__(self) -> None:
        super().__init__()
        self.count_reads = 0

    async def access_counts(self, investigation_id: str):  # type: ignore[no-untyped-def]
        self.count_reads += 1
        return await super().access_counts(investigation_id)


async def _cached_service() -> tuple[WorkingSetService, _CountingStore]:
    store = _CountingStore()
    await store.add_nodes(CASE, [node("a"), node("b"), node("s", "SECRET")])
    await store.add_edges(CASE, [edge("ab", "a", "b"), edge("as", "a", "s")])
    return _service(store), store


async def test_the_readable_signatures_are_kept_for_a_reader_and_a_case_that_has_not_changed() -> (
    None
):
    service, _ = await _cached_service()
    first = await service._reader_counts(CASE, OFFICIAL_READER)
    held = dict(service._readable)

    second = await service._reader_counts(CASE, OFFICIAL_READER)

    assert first.readable == second.readable and (first.nodes, first.edges) == (2, 1)
    assert service._readable == held and len(held) == 1


async def test_a_signature_first_stored_is_a_new_key_and_the_reader_may_read_it() -> None:
    """Violation caught: a key without the signatures version, which keeps the readable set the
    case had before it gained a signature, so the new nodes are counted to no one."""
    service, store = await _cached_service()
    before = await service._reader_counts(CASE, OFFICIAL_READER)

    await store.add_nodes(CASE, [node("x").model_copy(update={"datasets": ["enron"]})])
    after = await service._reader_counts(CASE, OFFICIAL_READER)

    assert before.nodes == 2 and after.nodes == 3


async def test_a_case_that_starts_again_is_not_taken_for_the_case_before() -> None:
    """Violation caught: a key without the epoch. `clear` drops the signatures' keys, which start
    again at 1, so the same version and the same key can name a different signature."""
    store = FakeWorkingSetStore()
    service = _service(store)
    await store.add_nodes(CASE, [node("a")])
    first = await service._reader_counts(CASE, OFFICIAL_READER)  # signature 'official' readable
    await store.clear(CASE)
    await store.add_nodes(CASE, [node("a", "SECRET")])  # one signature again, now above the reader
    second = await service._reader_counts(CASE, OFFICIAL_READER)

    assert first.nodes == 1 and second.nodes == 0


async def test_a_reader_of_another_access_class_is_never_given_the_first_readers_readable_set() -> (
    None
):
    """Violation caught (rule 3): a key without the access class, so a SECRET reader after an
    OFFICIAL one is counted the OFFICIAL view (missing what they may read), or an OFFICIAL reader
    after a SECRET one is counted the SECRET view (a hidden node and the link to it)."""
    service, _ = await _cached_service()
    official = await service._reader_counts(CASE, OFFICIAL_READER)
    secret = await service._reader_counts(CASE, SECRET_READER)
    official_again = await service._reader_counts(CASE, OFFICIAL_READER)

    assert (official.nodes, official.edges) == (2, 1)
    assert (secret.nodes, secret.edges) == (3, 2)
    assert (official_again.nodes, official_again.edges) == (2, 1)
    assert official.readable != secret.readable


async def test_two_readers_of_one_access_class_share_a_readable_set() -> None:
    service, _ = await _cached_service()
    await service._reader_counts(CASE, OFFICIAL_READER)
    twin = OFFICIAL_READER.model_copy(update={"id": "someone-else"})

    await service._reader_counts(CASE, twin)

    assert len(service._readable) == 1
    assert principal_class(twin) == principal_class(OFFICIAL_READER)


async def test_the_readable_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "READABLE_CACHE_SIZE", 4)
    service, store = await _cached_service()
    for i in range(20):
        await store.add_nodes(CASE, [node(f"n{i}").model_copy(update={"datasets": [f"d{i}"]})])
        await service._reader_counts(CASE, OFFICIAL_READER)

    assert 0 < len(service._readable) <= 4


async def test_a_menu_of_previews_reads_only_small_things_and_never_a_body() -> None:
    from schemas.domain import ExpandRequest

    class NoBodies(_CountingStore):
        async def source_fidelity_nodes(self, investigation_id: str):  # type: ignore[no-untyped-def]
            raise AssertionError("a preview reads no node bodies")

        async def source_fidelity_edges(self, investigation_id: str):  # type: ignore[no-untyped-def]
            raise AssertionError("a preview reads no link bodies")

        async def node_ids(self, investigation_id: str):  # type: ignore[no-untyped-def]
            raise AssertionError("a preview does not list every stored node")

        async def edge_ids(self, investigation_id: str):  # type: ignore[no-untyped-def]
            raise AssertionError("a preview does not list every stored link")

    store = NoBodies()
    await store.add_nodes(CASE, [node("a"), node("b")])
    await store.add_edges(CASE, [edge("ab", "a", "b")])
    service = _service(store)

    for edge_type in (None, "ASSOCIATE_OF", "FAMILY_OF", "USES"):
        request = ExpandRequest(
            node_ids=["a"], depth=1, edge_types=None if edge_type is None else [edge_type]
        )
        preview = await service.expand_preview(CASE, request, OFFICIAL_READER)
        assert (preview.candidate_node_count, preview.candidate_edge_count) == (2, 1)


# --- restore keeps the index consistent --------------------------------------------------------


async def test_restore_leaves_every_structure_equal_to_the_bodies() -> None:
    """Violation caught: the reconcile removes stale ids and adds the target's through the store
    methods; one that bypassed them would leave the index describing the set before the restore."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("old-1"), node("old-2"), node("keep")])
    await store.add_edges(
        CASE, [edge("old-edge", "old-1", "keep"), edge("keep-edge", "keep", "old-2")]
    )
    service = _service(store)

    snapshot = await service.restore(
        CASE,
        [node("new-1"), node("new-2"), node("keep", "SECRET")],
        [edge("new-edge", "new-1", "new-2"), edge("to-raised", "new-1", "keep")],
        SECRET_READER,
    )

    assert {n.id for n in snapshot.nodes} == {"new-1", "new-2", "keep"}
    await assert_index_matches_bodies(store, CASE, "after restore")
    assert set((await store.counted_index(CASE)).nodes) == {"new-1", "new-2", "keep"}


async def test_random_service_writes_leave_every_structure_equal_to_the_bodies() -> None:
    """The service's own writes (seed, remove, restore) through the same store: after each, the
    index equals the bodies."""
    rng = random.Random(7)
    store = FakeWorkingSetStore()
    service = _service(store)
    for step in range(30):
        nodes: list[Node] = [random_node(rng, f"n{i}") for i in rng.sample(range(8), 3)]
        edges: list[Edge] = [random_edge(rng, f"e{i}") for i in rng.sample(range(10), 3)]
        action = rng.choice(["seed", "remove", "restore"])
        if action == "seed":
            await service.seed(CASE, nodes, edges, SECRET_READER)
        elif action == "remove":
            await service.remove(CASE, [n.id for n in nodes])
        else:
            await service.restore(CASE, nodes, edges, SECRET_READER)
        await assert_index_matches_bodies(store, CASE, f"step {step} {action}")


def test_the_oracle_counts_a_link_by_the_signatures_of_its_ends() -> None:
    nodes = {"a": node("a"), "s": node("s", "SECRET")}
    edges = {"as": edge("as", "a", "s"), "ax": edge("ax", "a", "x")}
    index = build_counted_index(nodes, edges)
    official, secret = _sig(node("a")), _sig(node("s", "SECRET"))
    assert index.node_counts == {official: 1, secret: 1}
    assert index.edge_counts == {(official, official, secret): 1, (official, official, ABSENT): 1}
    assert index.adjacency == {("a", "as"), ("s", "as"), ("a", "ax"), ("x", "ax")}


def test_the_datasets_a_signature_names_are_the_ones_the_generator_varies() -> None:
    assert [] in DATASET_SETS and ["enron", "fixture"] in DATASET_SETS
