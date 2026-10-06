"""Test-only lifecycle for the `RecognisePort` conformance suite: a client of a live
`ner` sidecar at `OSPREY_RECOGNISER_URL` (default `http://localhost:8090`, where a test run
starts one)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .adapter import RecogniserConfig, RecogniseStanzaAdapter


@asynccontextmanager
async def recognise_stanza_adapter() -> AsyncIterator[RecogniseStanzaAdapter]:
    adapter = RecogniseStanzaAdapter(
        RecogniserConfig(base_url=os.environ.get("OSPREY_RECOGNISER_URL", "http://localhost:8090"))
    )
    try:
        yield adapter
    finally:
        await adapter.aclose()
