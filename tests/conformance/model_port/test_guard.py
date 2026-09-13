"""Guard test for the `ModelPort` conformance suite — Phase 0 plan §2.A."""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import MODEL_PORT_ADAPTERS


def test_model_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.model_port.test_suite")


def test_model_port_registry_is_empty_in_phase_0() -> None:
    assert MODEL_PORT_ADAPTERS == []
