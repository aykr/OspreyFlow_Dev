"""`_pending_port_placeholders.py` must not outlive the phases that replace it.

`GraphPort`'s placeholder types moved to the real domain model
(`schemas/domain.py`) in Phase 1 once `graph_arcadedb` was registered —
`_phase0_placeholders.py` is gone (`docs/07_BUILD_PLAN.md` Phase 1 exit
criterion). `AnalyticsPort`/`ComputePort`/`ModelPort` have no adapter yet, so
their stand-ins live on in `_pending_port_placeholders.py` until Phases 2, 6
and 7 replace them one port at a time.
"""

from __future__ import annotations

import importlib.util

from tests.conformance.registry import (
    ANALYTICS_PORT_ADAPTERS,
    COMPUTE_PORT_ADAPTERS,
    MODEL_PORT_ADAPTERS,
)


def test_pending_placeholders_exist_only_while_their_three_registries_are_empty() -> None:
    all_pending_registries_empty = not any(
        (ANALYTICS_PORT_ADAPTERS, COMPUTE_PORT_ADAPTERS, MODEL_PORT_ADAPTERS)
    )
    placeholders_module_exists = (
        importlib.util.find_spec("schemas._pending_port_placeholders") is not None
    )
    assert placeholders_module_exists == all_pending_registries_empty, (
        "packages/schemas/_pending_port_placeholders.py must exist iff "
        "ANALYTICS_PORT_ADAPTERS, COMPUTE_PORT_ADAPTERS and MODEL_PORT_ADAPTERS "
        "(tests/conformance/registry.py) are all still empty."
    )


def test_phase0_placeholders_module_is_gone() -> None:
    """`GRAPH_PORT_ADAPTERS` is non-empty from Phase 1 on, so this module
    must never come back — see `tests/conformance/graph_port/test_guard.py`
    for the corresponding registry-population assertion."""
    assert importlib.util.find_spec("schemas._phase0_placeholders") is None
