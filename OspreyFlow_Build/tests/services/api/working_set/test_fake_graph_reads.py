"""`FakeGraphPort.get_nodes` and `get_edges` (ADR-124 U1) refuse what the adapter refuses, so a
test that reads through them is not run against something more permissive than the Vault
(`CLAUDE.md` rule 15's second worked example). The fake's older `get_node` returns a visible node
for any id not marked hidden, an absent id included; these two do not. The adapter's own refusals
are proved by the conformance suite, against ArcadeDB; this file proves only the fake."""

from __future__ import annotations

import pytest

from schemas.domain import Edge, Node, Principal, Subgraph

from .fakes import FakeGraphPort
from .test_service import PRINCIPAL, _edge, _node

SECRET_READER = Principal(id="analyst-secret", clearance="SECRET", org_unit="unit-1")
ENRON_READER = Principal(
    id="analyst-enron", clearance="OFFICIAL", org_unit="unit-1", datasets=["enron"]
)
#: Owns the restricted code `R` below: the record's own unit, and receives `R`.
UNIT_R_READER = Principal(
    id="analyst-r", clearance="OFFICIAL", org_unit="unit-r", receivable_handling_codes=["R"]
)


def _with[E: (Node, Edge)](
    element: E,
    *,
    classification: str | None = None,
    handling_code: str | None = None,
    owning_unit: str | None = None,
    datasets: list[str] | None = None,
    superseded_by: str | None = None,
    reverted: bool = False,
) -> E:
    """The element with one of its own body fields changed: what the fake is to judge it by."""
    handling = {
        k: v
        for k, v in {
            "classification": classification,
            "handling_code": handling_code,
            "owning_unit": owning_unit,
        }.items()
        if v is not None
    }
    audit = {"superseded_by": superseded_by, "reverted": reverted}
    return element.model_copy(
        update={
            "handling": element.handling.model_copy(update=handling),
            "audit": element.audit.model_copy(update=audit),
            **({"datasets": datasets} if datasets is not None else {}),
        }
    )


def _world(nodes: list[Node], edges: list[Edge] | None = None) -> FakeGraphPort:
    return FakeGraphPort(Subgraph(nodes=[], edges=[]), graph_nodes=nodes, graph_edges=edges or [])


def _graph(
    *,
    hidden: frozenset[str] = frozenset(),
    superseded: frozenset[str] = frozenset(),
    hidden_edges: frozenset[str] = frozenset(),
    superseded_edges: frozenset[str] = frozenset(),
    edges: list[Edge] | None = None,
) -> FakeGraphPort:
    nodes = [_node(name) for name in ("a", "b", "c", "d", "e")]
    return FakeGraphPort(
        Subgraph(nodes=[], edges=[]),
        hidden_node_ids=hidden,
        graph_nodes=nodes,
        superseded_node_ids=superseded,
        graph_edges=edges or [],
        hidden_edge_ids=hidden_edges,
        superseded_edge_ids=superseded_edges,
    )


async def test_get_nodes_returns_the_readable_nodes_ordered_by_id() -> None:
    graph = _graph()
    nodes = await graph.get_nodes(["c", "a", "b"], PRINCIPAL)
    assert [n.id for n in nodes] == ["a", "b", "c"]


async def test_get_nodes_leaves_out_an_absent_id() -> None:
    graph = _graph()
    assert await graph.get_nodes(["no-such-node"], PRINCIPAL) == []
    assert [n.id for n in await graph.get_nodes(["no-such-node", "a"], PRINCIPAL)] == ["a"]


async def test_get_nodes_leaves_out_a_hidden_id() -> None:
    graph = _graph(hidden=frozenset({"b"}))
    assert await graph.get_nodes(["b"], PRINCIPAL) == []
    assert [n.id for n in await graph.get_nodes(["a", "b", "c"], PRINCIPAL)] == ["a", "c"]


async def test_get_nodes_leaves_out_a_superseded_id() -> None:
    graph = _graph(superseded=frozenset({"d"}))
    assert await graph.get_nodes(["d"], PRINCIPAL) == []
    assert [n.id for n in await graph.get_nodes(["d", "e"], PRINCIPAL)] == ["e"]


async def test_get_nodes_gives_absent_hidden_and_superseded_the_same_answer() -> None:
    graph = _graph(hidden=frozenset({"b"}), superseded=frozenset({"d"}))
    assert (
        await graph.get_nodes(["no-such-node"], PRINCIPAL)
        == await graph.get_nodes(["b"], PRINCIPAL)
        == await graph.get_nodes(["d"], PRINCIPAL)
        == []
    )
    mixed = await graph.get_nodes(["no-such-node", "b", "d", "a"], PRINCIPAL)
    assert mixed == await graph.get_nodes(["a"], PRINCIPAL)


async def test_get_nodes_returns_a_duplicated_id_once_and_no_ids_give_nothing() -> None:
    graph = _graph()
    assert [n.id for n in await graph.get_nodes(["b", "a", "b", "a"], PRINCIPAL)] == ["a", "b"]
    assert await graph.get_nodes([], PRINCIPAL) == []


async def test_get_nodes_records_the_request_with_its_principal() -> None:
    graph = _graph()
    await graph.get_nodes(["a", "b"], PRINCIPAL)
    assert graph.get_nodes_requests == [(["a", "b"], PRINCIPAL)]


async def test_get_edges_returns_a_link_whose_two_ends_are_readable() -> None:
    graph = _graph(edges=[_edge("e2", "c", "d"), _edge("e1", "a", "b")])
    edges = await graph.get_edges(["e2", "e1"], PRINCIPAL)
    assert [e.id for e in edges] == ["e1", "e2"]


async def test_get_edges_leaves_out_an_absent_id() -> None:
    graph = _graph(edges=[_edge("e1", "a", "b")])
    assert await graph.get_edges(["no-such-link"], PRINCIPAL) == []


async def test_get_edges_leaves_out_a_hidden_link() -> None:
    graph = _graph(hidden_edges=frozenset({"e1"}), edges=[_edge("e1", "a", "b")])
    assert await graph.get_edges(["e1"], PRINCIPAL) == []


async def test_get_edges_leaves_out_a_superseded_link() -> None:
    graph = _graph(superseded_edges=frozenset({"e1"}), edges=[_edge("e1", "a", "b")])
    assert await graph.get_edges(["e1"], PRINCIPAL) == []


async def test_get_edges_leaves_out_a_readable_link_with_a_hidden_end() -> None:
    graph = _graph(hidden=frozenset({"b"}), edges=[_edge("e1", "a", "b"), _edge("e2", "a", "c")])
    assert [e.id for e in await graph.get_edges(["e1", "e2"], PRINCIPAL)] == ["e2"]


async def test_get_edges_leaves_out_a_link_with_a_superseded_end_or_an_absent_end() -> None:
    graph = _graph(
        superseded=frozenset({"d"}),
        edges=[_edge("e1", "a", "d"), _edge("e2", "a", "nowhere"), _edge("e3", "a", "b")],
    )
    assert [e.id for e in await graph.get_edges(["e1", "e2", "e3"], PRINCIPAL)] == ["e3"]


async def test_get_edges_gives_every_refusal_the_same_answer() -> None:
    graph = _graph(
        hidden=frozenset({"b"}),
        hidden_edges=frozenset({"e2"}),
        superseded_edges=frozenset({"e3"}),
        edges=[
            _edge("e1", "a", "b"),
            _edge("e2", "a", "c"),
            _edge("e3", "a", "d"),
            _edge("e4", "a", "e"),
        ],
    )
    for refused in ("no-such-link", "e1", "e2", "e3"):
        assert await graph.get_edges([refused], PRINCIPAL) == []
    mixed = await graph.get_edges(["no-such-link", "e1", "e2", "e3", "e4"], PRINCIPAL)
    assert mixed == await graph.get_edges(["e4"], PRINCIPAL)


async def test_get_edges_returns_a_duplicated_id_once_and_no_ids_give_nothing() -> None:
    graph = _graph(edges=[_edge("e1", "a", "b"), _edge("e2", "b", "c")])
    assert [e.id for e in await graph.get_edges(["e2", "e1", "e2"], PRINCIPAL)] == ["e1", "e2"]
    assert await graph.get_edges([], PRINCIPAL) == []


async def test_get_edges_records_the_request_with_its_principal() -> None:
    graph = _graph(edges=[_edge("e1", "a", "b")])
    await graph.get_edges(["e1"], PRINCIPAL)
    assert graph.get_edges_requests == [(["e1"], PRINCIPAL)]


# --- the fake judges each element by its own body, for the principal given (ADR-124 U1) ----------
#
# The explicit sets above are overrides. What the adapter does, the fake does: the handling
# predicate, the case's datasets, a superseded body, a reverted body.


async def test_get_nodes_judges_a_node_by_its_own_classification_for_each_principal() -> None:
    world = _world([_with(_node("a"), classification="SECRET"), _node("b")])
    assert [n.id for n in await world.get_nodes(["a", "b"], PRINCIPAL)] == ["b"]
    assert [n.id for n in await world.get_nodes(["a", "b"], SECRET_READER)] == ["a", "b"]


async def test_get_nodes_judges_a_restricted_code_by_the_readers_unit_and_receivable_codes() -> (
    None
):
    node = _with(_node("a"), handling_code="R", owning_unit="unit-r")
    world = _world([node])
    assert await world.get_nodes(["a"], PRINCIPAL) == []  # right clearance, not the unit
    assert [n.id for n in await world.get_nodes(["a"], UNIT_R_READER)] == ["a"]
    no_code = UNIT_R_READER.model_copy(update={"receivable_handling_codes": []})
    assert await world.get_nodes(["a"], no_code) == []


async def test_get_nodes_leaves_out_a_node_whose_own_body_is_superseded_or_reverted() -> None:
    world = _world(
        [
            _with(_node("old"), superseded_by="new"),
            _node("new"),
            _with(_node("gone"), reverted=True),
        ]
    )
    assert [n.id for n in await world.get_nodes(["old", "new", "gone"], SECRET_READER)] == ["new"]


async def test_get_nodes_leaves_out_a_node_of_another_dataset() -> None:
    world = _world(
        [
            _with(_node("e"), datasets=["enron"]),
            _with(_node("f"), datasets=["fixture"]),
            _with(_node("both"), datasets=["enron", "fixture"]),
        ]
    )
    assert [n.id for n in await world.get_nodes(["e", "f", "both"], ENRON_READER)] == ["both", "e"]
    nothing = ENRON_READER.model_copy(update={"datasets": []})
    assert await world.get_nodes(["e", "f", "both"], nothing) == []
    assert len(await world.get_nodes(["e", "f", "both"], PRINCIPAL)) == 3  # `None` is unlimited


async def test_get_nodes_finds_a_node_the_expansion_returns_without_graph_nodes() -> None:
    graph = FakeGraphPort(Subgraph(nodes=[_node("x"), _node("y")], edges=[_edge("xy", "x", "y")]))
    assert [n.id for n in await graph.get_nodes(["y", "x", "z"], PRINCIPAL)] == ["x", "y"]
    assert [e.id for e in await graph.get_edges(["xy"], PRINCIPAL)] == ["xy"]


async def test_get_edges_judges_a_link_by_its_own_body_for_the_principal_given() -> None:
    nodes = [_with(_node(n), datasets=["enron"]) for n in "abcdef"]
    enron = ["enron"]
    world = _world(
        nodes,
        [
            _with(_edge("secret", "a", "b"), classification="SECRET", datasets=enron),
            _with(_edge("old", "a", "c"), superseded_by="new", datasets=enron),
            _with(_edge("gone", "a", "d"), reverted=True, datasets=enron),
            _with(_edge("other", "a", "e"), datasets=["fixture"]),
            _with(_edge("mine", "a", "f"), datasets=enron),
        ],
    )
    asked = ["secret", "old", "gone", "other", "mine"]
    # Every id but "mine" is left out for its own reason: each is in the reader's dataset but one.
    assert [e.id for e in await world.get_edges(asked, ENRON_READER)] == ["mine"]
    # And a reader who differs in just that one axis reads it.
    secret_in_enron = SECRET_READER.model_copy(update={"datasets": enron})
    assert [e.id for e in await world.get_edges(["secret"], secret_in_enron)] == ["secret"]
    both = ENRON_READER.model_copy(update={"datasets": ["enron", "fixture"]})
    assert [e.id for e in await world.get_edges(["other"], both)] == ["other"]


async def test_get_edges_judges_each_end_by_its_own_body() -> None:
    enron = ["enron"]
    world = _world(
        [
            _with(_node("a"), datasets=enron),
            _with(_node("secret_end"), classification="SECRET", datasets=enron),
            _with(_node("reverted_end"), reverted=True, datasets=enron),
            _with(_node("other_end"), datasets=["fixture"]),
            _with(_node("r_end"), handling_code="R", owning_unit="unit-r", datasets=enron),
        ],
        [
            _with(_edge("to-secret", "a", "secret_end"), datasets=enron),
            _with(_edge("from-secret", "secret_end", "a"), datasets=enron),
            _with(_edge("to-reverted", "a", "reverted_end"), datasets=enron),
            _with(_edge("to-other", "a", "other_end"), datasets=enron),
            _with(_edge("to-r", "a", "r_end"), datasets=enron),
        ],
    )
    for link in ("to-secret", "from-secret", "to-reverted", "to-r"):
        assert await world.get_edges([link], PRINCIPAL) == [], link
    assert [e.id for e in await world.get_edges(["to-secret", "from-secret"], SECRET_READER)] == [
        "from-secret",
        "to-secret",
    ]
    assert await world.get_edges(["to-other"], ENRON_READER) == []
    both = ENRON_READER.model_copy(update={"datasets": ["enron", "fixture"]})
    assert [e.id for e in await world.get_edges(["to-other"], both)] == ["to-other"]
    assert [e.id for e in await world.get_edges(["to-r"], UNIT_R_READER)] == ["to-r"]


async def test_edges_among_judges_a_link_and_its_held_ends_by_their_own_bodies() -> None:
    world = _world(
        [_node("a"), _node("b"), _with(_node("s"), classification="SECRET")],
        [
            _edge("ab", "a", "b"),
            _with(_edge("ab-secret", "a", "b"), classification="SECRET"),
            _edge("as", "a", "s"),
        ],
    )
    assert [e.id for e in await world.edges_among(["a", "b", "s"], PRINCIPAL)] == ["ab"]
    among = await world.edges_among(["a", "b", "s"], SECRET_READER)
    assert {e.id for e in among} == {"ab", "ab-secret", "as"}


async def test_the_reads_refuse_a_bare_string_for_the_ids_as_the_adapter_does() -> None:
    graph = _graph(edges=[_edge("e1", "a", "b")])
    with pytest.raises(TypeError):
        await graph.get_nodes("abc", PRINCIPAL)
    with pytest.raises(TypeError):
        await graph.get_edges("e1", PRINCIPAL)
