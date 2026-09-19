"""Guard test for the `ComputePort` conformance suite — Phase 7 Stage 3's own handover.

`COMPUTE_PORT_ADAPTERS` was asserted empty through Stage 2; this is the guard turning red on
purpose (`adapters/compute_rustworkx` now registers), the same expected handover
`graph_port/test_guard.py` went through in Phase 1 and `analytics_port/test_guard.py` in Phase 2 —
not a regression to work around.
"""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import COMPUTE_PORT_ADAPTERS


def test_compute_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.compute_port.test_suite")


def test_compute_port_registry_is_populated_from_phase_7_stage_3() -> None:
    assert COMPUTE_PORT_ADAPTERS != []
    for factory in COMPUTE_PORT_ADAPTERS:
        assert factory.label
