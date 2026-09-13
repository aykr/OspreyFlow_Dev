"""`_phase0_placeholders.py` must not outlive Phase 1 — Phase 0 plan §2.B / §4.

The moment any port has a registered adapter, the placeholder module is
required to be gone, replaced by the real domain model
(`docs/01_DOMAIN_MODEL.md`). Phase 0 has no registered adapters anywhere, so
the placeholder module is expected to still exist — this test asserts the
equivalence in both directions so it isn't vacuous today.
"""

from __future__ import annotations

import importlib.util

from tests.conformance.registry import (
    ANALYTICS_PORT_ADAPTERS,
    COMPUTE_PORT_ADAPTERS,
    GRAPH_PORT_ADAPTERS,
    MODEL_PORT_ADAPTERS,
)


def test_placeholders_exist_only_while_every_registry_is_empty() -> None:
    all_registries_empty = not any(
        (
            GRAPH_PORT_ADAPTERS,
            ANALYTICS_PORT_ADAPTERS,
            COMPUTE_PORT_ADAPTERS,
            MODEL_PORT_ADAPTERS,
        )
    )
    placeholders_module_exists = (
        importlib.util.find_spec("schemas._phase0_placeholders") is not None
    )
    assert placeholders_module_exists == all_registries_empty, (
        "packages/schemas/_phase0_placeholders.py must exist iff every port's adapter "
        "registry (tests/conformance/registry.py) is still empty — see Phase 0 plan §2.B."
    )
