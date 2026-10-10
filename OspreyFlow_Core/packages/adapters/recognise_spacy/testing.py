"""Test-only lifecycle for the `RecognisePort` conformance suite: the in-process spaCy adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .adapter import RecogniseSpacyAdapter


@asynccontextmanager
async def recognise_spacy_adapter() -> AsyncIterator[RecogniseSpacyAdapter]:
    adapter = RecogniseSpacyAdapter()
    try:
        yield adapter
    finally:
        await adapter.aclose()
