"""Guard test for the `GraphPort` conformance suite — Phase 1 handover.

`GRAPH_PORT_ADAPTERS` was asserted empty through Phase 0; this is the guard
turning red on purpose, per the Phase 1 exit criterion
(`docs/07_BUILD_PLAN.md`) — the expected handover once `graph_arcadedb` is
registered, not a regression.
"""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import GRAPH_PORT_ADAPTERS


def test_graph_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.graph_port.test_suite")


def test_graph_port_registry_is_populated_from_phase_1() -> None:
    assert GRAPH_PORT_ADAPTERS != []
    known_dialects = ("gremlin", "opencypher", "gql")
    assert all(factory.dialect in known_dialects for factory in GRAPH_PORT_ADAPTERS)
