"""An OFFICIAL analyst's expansion carries no count from which a SECRET link could be inferred
(ADR-122; rules 3 and 7).

`Edge.weight_components` holds degrees counted over the whole store, a SECRET link included. A
response that carries them lets an OFFICIAL analyst see that a node has more links than they can
read. Uses the **real** `graph_arcadedb` adapter and `WorkingSetService.expand`, serialised as
the expand route returns it (`model_dump(mode="json")`), so the counts are the adapter's own.
"""

from __future__ import annotations

import pytest
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import ExpandRequest, Principal
from tests.conformance.graph_port.test_suite import _edge, _node, _past_interval, _write
from tests.conformance.registry import GRAPH_PORT_ADAPTERS, GraphAdapterFactory

from ..corpus_counts import FORBIDDEN_KEYS, keys_at_any_depth
from .fakes import FakeWorkingSetStore

pytestmark = pytest.mark.parametrize("factory", GRAPH_PORT_ADAPTERS, ids=str)

OFFICIAL = Principal(id="analyst-official", clearance="OFFICIAL", org_unit="unit-1")


async def test_an_official_analyst_s_expansion_carries_no_count_that_reveals_a_secret_link(
    factory: GraphAdapterFactory,
) -> None:
    """Violated by a response that carries `weight_components` (or any of the four corpus counts)
    on a link the analyst may read. Node `a` has a SECRET link to `d` at 40 occurrences, written
    first, and an OFFICIAL link to `b` at 2, written after it, so the OFFICIAL link stores a
    degree of 42 at `a` and a type total of 42: counts that reveal the SECRET link to a reader who
    sees only the OFFICIAL one. The case first proves in Python that the leak exists in what the
    service returns (the stored 42), so a fixture that holds no leak cannot pass for the wire's
    silence. Also violated by the SECRET link, or its far end, reaching the response at all."""
    async with factory.context() as graph:
        (a, b, d), _ = await _write(
            graph,
            [
                _node("Endpoint", classification="OFFICIAL", value_normalised="+441111111111"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+442222222222"),
                _node("Endpoint", classification="OFFICIAL", value_normalised="+443333333333"),
            ],
            [],
        )
        interval = _past_interval()
        _, (hidden,) = await _write(
            graph,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    d,
                    classification="SECRET",
                    occurrences=40,
                    interval=interval,
                )
            ],
        )
        _, (visible,) = await _write(
            graph,
            [],
            [
                _edge(
                    "COMMUNICATED_WITH",
                    a,
                    b,
                    classification="OFFICIAL",
                    occurrences=2,
                    interval=interval,
                )
            ],
        )

        service = WorkingSetService(graph, FakeWorkingSetStore(), load_uk_le_scheme())
        outcome = await service.expand("inv-1", ExpandRequest(node_ids=[a], depth=1), OFFICIAL)

        in_python = {e.id: e for e in outcome.delta.edges}
        assert visible in in_python, "the OFFICIAL link must be sent, or the case proves nothing"
        assert hidden not in in_python
        components = in_python[visible].weight_components
        assert components is not None, "the link is read back without its components"
        assert components.corpus_source_degree == 42, "the count that would reveal the SECRET link"
        assert components.corpus_total_occurrences == 42

        wire = outcome.model_dump(mode="json")
        sent_ids = {e["id"] for e in wire["delta"]["edges"]}
        assert sent_ids == {visible}
        assert d not in {n["id"] for n in wire["delta"]["nodes"]}
        assert keys_at_any_depth(wire) & FORBIDDEN_KEYS == set()
