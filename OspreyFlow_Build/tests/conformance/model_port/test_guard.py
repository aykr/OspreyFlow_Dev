"""Guard test for the `ModelPort` conformance suite — Phase 6 Stage 1 handover.

`MODEL_PORT_ADAPTERS` was asserted empty through Phase 5; this is the guard turning red on
purpose, per this phase's own stage — the expected handover once
`adapters/model_litellm` is registered, not a regression.
"""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import MODEL_PORT_ADAPTERS


def test_model_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.model_port.test_suite")


def test_model_port_registry_is_populated_from_phase_6() -> None:
    assert MODEL_PORT_ADAPTERS != []


def test_model_port_extract_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.model_port.test_suite_extract")


def test_the_model_port_suite_holds_both_extraction_engines() -> None:
    """ADR-135 Amendment 6: Laurium is registered for `test_suite.py`'s own extract cases, live,
    and offers `extract` alone, so every other case skips it saying so, never silently."""
    by_label = {str(f): f for f in MODEL_PORT_ADAPTERS}
    assert list(by_label) == ["model_litellm", "extract_laurium"]
    assert by_label["extract_laurium"].offers == frozenset({"extract"})


def test_the_extract_suite_holds_both_engines() -> None:
    """ADR-135 Amendment 6: Deep read's adapter and Laurium's, one suite for both."""
    from tests.conformance.model_port.extract_engines import MODEL_EXTRACT_ADAPTERS

    assert [str(f) for f in MODEL_EXTRACT_ADAPTERS] == ["model_litellm", "extract_laurium"]
