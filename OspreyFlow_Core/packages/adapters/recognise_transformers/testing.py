"""Test-only lifecycle for the `RecognisePort` conformance suite: the in-process HF adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .adapter import RecogniseTransformersAdapter


@asynccontextmanager
async def recognise_transformers_adapter() -> AsyncIterator[RecogniseTransformersAdapter]:
    adapter = RecogniseTransformersAdapter()
    try:
        yield adapter
    finally:
        await adapter.aclose()
