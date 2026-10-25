"""`/seed` against the real graph adapter (ADR-124 decision 7, rules 3, 4 and 15): live.

`test_seed_verifies_against_the_vault.py` holds the service's rules against a fake whose by-id reads
refuse what the adapter refuses. This is the other half, the one a fake cannot give (rule 15: a
fake that accepted what the real dependency refuses would let the defect pass): real nodes and links
written to the throwaway database, and a seed that submits bodies forged to look readable. Uses the
real `get_nodes` and `get_edges` of every adapter in `GRAPH_PORT_ADAPTERS`, through
`WorkingSetService.seed`, the one path all of `/seed`'s callers go through.

Run it with the graph suite's own settings (the throwaway ArcadeDB); it needs the stack.
"""

from __future__ import annotations

import pytest
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import Edge, Node, Principal
from tests.conformance.graph_port.test_suite import (
    _edge,
    _node,
    _past_interval,
    _write,
)
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

from .fakes import FakeWorkingSetStore
from .test_visible_link import edge as forged_edge
from .test_visible_link import node as forged_body

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

CASE = "inv-1"
SCHEME = load_uk_le_scheme()
OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")
REAL = {"ok1": "+441110000001", "ok2": "+441110000002", "secret": "+441110000003"}


def _forged(node_id: str) -> Node:
    return forged_body(node_id, "OFFICIAL").model_copy(update={"properties": {"name": "forged"}})


class _Written:
    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.links: dict[str, str] = {}


async def _write_the_vault(graph: object) -> _Written:
    """`ok1` and `ok2` (OFFICIAL) with a link between them, a SECRET node with an OFFICIAL link to
    `ok1`, and a node that is then superseded."""
    written = _Written()
    ok1, ok2, secret, old = (
        await _write(
            graph,  # type: ignore[arg-type]
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised=REAL["ok1"]),
                _node("Endpoint", classification="OFFICIAL", value_normalised=REAL["ok2"]),
                _node("Endpoint", classification="SECRET", value_normalised=REAL["secret"]),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441110000004"),
            ],
            [],
        )
    )[0]
    written.ids = {"ok1": ok1, "ok2": ok2, "secret": secret, "old": old}
    interval = _past_interval()
    _, (between, to_secret) = await _write(
        graph,  # type: ignore[arg-type]
        [],
        [
            _edge("COMMUNICATED_WITH", ok1, ok2, classification="OFFICIAL", interval=interval),
            _edge("COMMUNICATED_WITH", ok1, secret, classification="OFFICIAL", interval=interval),
        ],
    )
    written.links = {"between": between, "to_secret": to_secret}
    tx = await graph.begin_transaction()  # type: ignore[attr-defined]
    await graph.supersede_node(  # type: ignore[attr-defined]
        old,
        _node("Endpoint", classification="OFFICIAL", value_normalised="+441110000005"),
        tx,
    )
    await graph.commit_transaction(tx)  # type: ignore[attr-defined]
    return written


async def test_seed_stores_the_vaults_bodies_and_refuses_forged_ones(
    factory: GraphAdapterFactory,
) -> None:
    """Violation caught (rule 3): forged bodies stored. A body marked OFFICIAL for the SECRET node,
    one for the superseded id, one for an id never written, and a link whose real end is hidden:
    the stored set holds the two real nodes (with the Vault's own properties) and the link
    between them, and nothing else."""
    async with factory.context() as graph:
        w = await _write_the_vault(graph)
        absent = "never-written-" + w.ids["ok1"][:8]
        store = FakeWorkingSetStore()
        service = WorkingSetService(graph, store, SCHEME)
        forged_links = [
            _forged_link(w.links["between"], w.ids["ok1"], w.ids["ok2"]),
            _forged_link(w.links["to_secret"], w.ids["ok1"], w.ids["secret"]),
        ]

        await service.seed(
            CASE,
            [
                _forged(i)
                for i in (w.ids["ok1"], w.ids["ok2"], w.ids["secret"], w.ids["old"], absent)
            ],
            forged_links,
            OFFICIAL,
        )

        stored = await store.source_fidelity_nodes(CASE)
        assert set(stored) == {w.ids["ok1"], w.ids["ok2"]}
        assert stored[w.ids["ok1"]].properties["value_normalised"] == REAL["ok1"]
        assert set(await store.source_fidelity_edges(CASE)) == {w.links["between"]}


def _forged_link(link_id: str, source: str, target: str) -> Edge:
    return forged_edge(link_id, source, target).model_copy(update={"properties": {"forged": True}})


async def test_a_hidden_a_superseded_and_an_absent_id_answer_alike_on_the_adapter(
    factory: GraphAdapterFactory,
) -> None:
    """Rule 4: `/seed` as a membership test. The response and the following snapshot are identical
    whether the second id seeded is a SECRET node, a superseded revision or an id never written."""
    answers = []
    async with factory.context() as graph:
        w = await _write_the_vault(graph)
        for unreadable in (w.ids["secret"], w.ids["old"], "never-written-" + w.ids["ok1"][:8]):
            store = FakeWorkingSetStore()
            service = WorkingSetService(graph, store, SCHEME)
            outcome = await service.seed(
                CASE, [_forged(w.ids["ok1"]), _forged(unreadable)], [], OFFICIAL
            )
            (snapshot,) = await service.sync(CASE, OFFICIAL, last_acknowledged_seq=None)
            answers.append((outcome.model_dump(mode="json"), snapshot.model_dump(mode="json")))

    assert answers[0] == answers[1] == answers[2]
    assert [n["id"] for n in answers[0][0]["delta"]["nodes"]] == [w.ids["ok1"]]


async def test_a_link_with_an_unverified_end_is_dropped_against_the_adapter(
    factory: GraphAdapterFactory,
) -> None:
    """Verify each link: `ok1`-`ok2` is readable with both ends readable, but only `ok1` is seeded
    and `ok2` is on nobody's canvas, so the link is not stored; once `ok2` is on the canvas it is.
    """
    async with factory.context() as graph:
        w = await _write_the_vault(graph)
        link = _forged_link(w.links["between"], w.ids["ok1"], w.ids["ok2"])
        store = FakeWorkingSetStore()
        service = WorkingSetService(graph, store, SCHEME)

        first = await service.seed(CASE, [_forged(w.ids["ok1"])], [link], OFFICIAL)
        assert first.delta.edges == []

        await service.seed(CASE, [_forged(w.ids["ok2"])], [], OFFICIAL)
        second = await service.seed(CASE, [_forged(w.ids["ok1"])], [link], OFFICIAL)
        assert [e.id for e in second.delta.edges] == [w.links["between"]]
