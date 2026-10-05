"""Guard test for the `MediaStore` conformance suite (ADR-094 step 2)."""

from __future__ import annotations

from tests.conformance._guard import suite_imports_cleanly
from tests.conformance.registry import MEDIA_STORE_ADAPTERS


def test_media_store_suite_imports_cleanly() -> None:
    assert suite_imports_cleanly("tests.conformance.media_store.test_suite")


def test_media_store_registry_is_populated() -> None:
    assert MEDIA_STORE_ADAPTERS != []
