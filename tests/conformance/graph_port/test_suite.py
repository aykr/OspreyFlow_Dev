"""`GraphPort` conformance suite (`docs/07_BUILD_PLAN.md` Phase 1, `00_ARCHITECTURE.md` §2.1).

Parametrised over `GRAPH_PORT_ADAPTERS` in `tests/conformance/registry.py`.
Empty in Phase 0 — zero cases collected, which is expected (see `test_guard.py`
for the assertion that this isn't silently masking a broken suite). Phase 1
registers `adapters/graph_arcadedb` in the registry and the real per-method and
access-control-leak assertions land in this function; the parametrisation
itself does not change.
"""

from __future__ import annotations

import pytest

from tests.conformance.registry import GRAPH_PORT_ADAPTERS


@pytest.mark.parametrize("adapter", GRAPH_PORT_ADAPTERS)
def test_graph_port_conformance(adapter: object) -> None:
    assert adapter is not None
