"""Guard test for the `RecognisePort` conformance suite (ADR-098 decision 2)."""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import RECOGNISE_PORT_ADAPTERS


def test_recognise_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.recognise_port.test_suite")


def test_recognise_port_registry_is_populated() -> None:
    assert RECOGNISE_PORT_ADAPTERS != []
