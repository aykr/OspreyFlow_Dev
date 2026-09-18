"""Guard test for the `ModelPort` conformance suite — Phase 6 Stage 1 handover.

`MODEL_PORT_ADAPTERS` was asserted empty through Phase 5; this is the guard turning red on
purpose, per Phase 6 Stage 1 (`docs/07_BUILD_PLAN.md`) — the expected handover once
`adapters/model_litellm` is registered, not a regression.
"""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import MODEL_PORT_ADAPTERS


def test_model_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.model_port.test_suite")


def test_model_port_registry_is_populated_from_phase_6() -> None:
    assert MODEL_PORT_ADAPTERS != []
