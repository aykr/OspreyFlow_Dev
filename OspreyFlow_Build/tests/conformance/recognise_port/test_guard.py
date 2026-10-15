"""Guard test for the `RecognisePort` conformance suite (ADR-098 decision 2)."""

from __future__ import annotations

import importlib.util

import pytest

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import RECOGNISE_PORT_ADAPTERS


def test_recognise_port_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.recognise_port.test_suite")


def test_recognise_port_registry_is_populated() -> None:
    assert RECOGNISE_PORT_ADAPTERS != []


def test_an_in_process_recogniser_is_offered_only_where_its_library_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapters import their libraries lazily, so importing an adapter proves nothing about
    the library; CI has neither spaCy nor transformers, and offering them there failed every case
    with ModuleNotFoundError (15 October 2026)."""
    from tests.conformance import registry

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: None if name in {"spacy", "transformers"} else real(name, *a, **k),
    )
    assert registry._recognise_in_process_factories() == []
