"""`_pending_port_placeholders.py` must not outlive the phases that replace it.

`GraphPort`'s placeholder types moved to the real domain model
(`schemas/domain.py`) in Phase 1 once `graph_arcadedb` was registered —
`_phase0_placeholders.py` is gone (`docs/07_BUILD_PLAN.md` Phase 1 exit
criterion). `AnalyticsPort`'s moved to `schemas/analytics.py` in Phase 2 once
`analytics_duckdb` was registered. `ComputePort`/`ModelPort` have no adapter
yet, so their stand-ins live on in `_pending_port_placeholders.py` until
Phases 6 and 7 replace them, one port at a time — the module itself is only
deleted once none are left.

Note on this test's history: through Phase 1, all three of
`ANALYTICS_PORT_ADAPTERS`/`COMPUTE_PORT_ADAPTERS`/`MODEL_PORT_ADAPTERS` were
simultaneously empty, so "the module exists iff all three registries are
empty" and "the module exists iff not all three are populated" agreed and
the difference was invisible. Phase 2 is the first point they diverge —
`ANALYTICS_PORT_ADAPTERS` populates while the other two stay empty — and the
first assertion, as originally written, demanded the module vanish
immediately, which would have deleted `ComputePort`/`ModelPort`'s still-live
placeholders. Corrected to the second condition, which is what the module's
own docstring always described.
"""

from __future__ import annotations

import importlib.util

from tests.conformance.registry import (
    ANALYTICS_PORT_ADAPTERS,
    COMPUTE_PORT_ADAPTERS,
    MODEL_PORT_ADAPTERS,
)


def test_pending_placeholders_exist_until_every_port_has_an_adapter() -> None:
    all_three_registries_populated = all(
        (ANALYTICS_PORT_ADAPTERS, COMPUTE_PORT_ADAPTERS, MODEL_PORT_ADAPTERS)
    )
    placeholders_module_exists = (
        importlib.util.find_spec("schemas._pending_port_placeholders") is not None
    )
    assert placeholders_module_exists != all_three_registries_populated, (
        "packages/schemas/_pending_port_placeholders.py must exist until "
        "ANALYTICS_PORT_ADAPTERS, COMPUTE_PORT_ADAPTERS and MODEL_PORT_ADAPTERS "
        "(tests/conformance/registry.py) are ALL non-empty — it is deleted only "
        "once every port has a real adapter."
    )


def test_phase0_placeholders_module_is_gone() -> None:
    """`GRAPH_PORT_ADAPTERS` is non-empty from Phase 1 on, so this module
    must never come back — see `tests/conformance/graph_port/test_guard.py`
    for the corresponding registry-population assertion."""
    assert importlib.util.find_spec("schemas._phase0_placeholders") is None
