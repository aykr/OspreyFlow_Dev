"""A fresh container per test on the Blob service at `AZURE_BLOB_ENDPOINT` (Azurite in CI and on a
laptop), for the `MediaStore` conformance suite (ADR-114 decision 8)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from . import BlobMediaStore, BlobStoreConfig


@asynccontextmanager
async def blob_media_store() -> AsyncIterator[BlobMediaStore]:
    base = BlobStoreConfig.from_env()
    store = BlobMediaStore(
        BlobStoreConfig(
            account=base.account,
            key=base.key,
            container=f"media-test-{uuid4().hex[:12]}",
            endpoint=base.endpoint,
        )
    )
    try:
        yield store
    finally:
        await store.aclose()
