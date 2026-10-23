"""The weight the Conduit sends for a link is the weight the store holds (ADR-120 D3; the Glass
draws the stored weight it is sent and recomputes none, `01_DOMAIN_MODEL.md` §6.1).

`WorkingSetService.expand` is what `POST /v1/investigations/{id}/expand` calls, and the delta it
returns is what the route serialises. Uses the **real** `graph_arcadedb` adapter, like the other
tests in this package, so the stored weight is the adapter's own.

Catches a service that recomputes a weight, rounds it or substitutes another on the way from the
store to the wire, for a counted link, a structural one (0.75) and a self-loop.
"""

from __future__ import annotations

import pytest
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import ExpandRequest, Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _past_interval, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

from .fakes import FakeWorkingSetStore

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")


async def test_the_weight_on_the_wire_is_the_stored_weight(factory: GraphAdapterFactory) -> None:
    async with factory.context() as graph:
        (a, b, p, q), _ = await _write(
            graph,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
                _node("Person", classification="OFFICIAL"),
                _node("Person", classification="OFFICIAL"),
            ],
            [],
        )
        interval = _past_interval()
        await _write(
            graph,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    occurrences=7,
                    interval=interval,
                ),
                _edge("FAMILY_OF", p, q, classification="OFFICIAL", interval=interval),
            ],
        )
        await _write(
            graph,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    a,
                    classification="OFFICIAL",
                    occurrences=3,
                    interval=interval,
                )
            ],
        )

        request = ExpandRequest(node_ids=[a, b, p, q], depth=1)
        # `expand` cannot return a self-loop (its walk's `simplePath()` step, `builders.py`,
        # `ExpandBuilder._repeat_clause`), so the stored weights are read through `edges_among`,
        # which can; the service brings those links among the view with the expansion.
        among = await graph.edges_among([a, b, p, q], OFFICIAL)
        stored = {e.id: e.weight for e in among}
        assert len(stored) == 3 and 0.75 in stored.values()
        assert sum(1 for e in among if e.source == e.target) == 1

        service = WorkingSetService(graph, FakeWorkingSetStore(), load_uk_le_scheme())
        outcome = await service.expand("inv-1", request, OFFICIAL)
        assert outcome.links_among == "added"

        sent = {e["id"]: e["weight"] for e in outcome.model_dump(mode="json")["delta"]["edges"]}
        assert sent == stored
        assert {e.id: e.weight for e in outcome.delta.edges} == stored
