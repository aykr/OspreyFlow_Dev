"""Test-only client lifecycle for the `ModelPort` conformance suite — mirrors
`adapters/graph_arcadedb/testing.py` and `adapters/analytics_duckdb/testing.py`'s per-test-instance
pattern. There is no per-test database to seed or drop here (LiteLLM/Ollama are stateless from this
adapter's point of view), so this only owns opening and closing the HTTP client cleanly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from . import CONFORMANCE_EMBED_MODEL
from .adapter import ModelLiteLLMAdapter
from .client import LiteLLMClient, LiteLLMConfig


@asynccontextmanager
async def model_litellm_adapter() -> AsyncIterator[ModelLiteLLMAdapter]:
    client = LiteLLMClient(LiteLLMConfig.from_env())
    try:
        yield ModelLiteLLMAdapter(client, embed_model=CONFORMANCE_EMBED_MODEL)
    finally:
        await client.aclose()
