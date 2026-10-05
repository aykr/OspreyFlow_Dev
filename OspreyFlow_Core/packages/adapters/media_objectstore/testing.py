"""Test contexts for the `MediaStore` conformance suite and for code that keeps files (ADR-094).

`InMemoryMediaStore` holds to the same reference rule as the object-store adapter, so a test that
uses it cannot pass with a reference the real store would refuse (`CLAUDE.md` rule 15)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from ports.media import MediaNotFoundError

from . import MediaStoreConfig, ObjectStoreMediaStore, checked, reference_for


class InMemoryMediaStore:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def put(self, data: bytes, content_type: str) -> str:
        ref = reference_for(data, content_type)
        self.files[ref] = data
        return ref

    async def get(self, ref: str) -> bytes:
        found = self.files.get(checked(ref))
        if found is None:
            raise MediaNotFoundError(ref)
        return found


@asynccontextmanager
async def in_memory_media_store() -> AsyncIterator[InMemoryMediaStore]:
    yield InMemoryMediaStore()


@asynccontextmanager
async def object_store_media_store() -> AsyncIterator[ObjectStoreMediaStore]:
    """A fresh bucket per test on the object store at `MINIO_ENDPOINT`."""
    base = MediaStoreConfig.from_env()
    config = MediaStoreConfig(
        endpoint=base.endpoint,
        access_key=base.access_key,
        secret_key=base.secret_key,
        bucket=f"media-test-{uuid4().hex[:12]}",
        use_ssl=base.use_ssl,
    )
    yield ObjectStoreMediaStore(config)
