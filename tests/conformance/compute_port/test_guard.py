"""Guard test for the `ComputePort` conformance suite — Phase 0 plan §2.A."""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import COMPUTE_PORT_ADAPTERS


def test_compute_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.compute_port.test_suite")


def test_compute_port_registry_is_empty_in_phase_0() -> None:
    assert COMPUTE_PORT_ADAPTERS == []
