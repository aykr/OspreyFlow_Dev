"""`MediaStore` — where a content item's file is kept (ADR-094 decision 3).

A file (an image, a video, a document's text) is never stored in the graph. The ingest engine puts
it here and writes a `Document` carrying the reference it gets back (`object_ref`); the reader and
extraction get it back by that reference. References are content-addressed, so the same file put
twice is kept once and gets the same reference, and a reference names nothing outside the store.

Who may read a file is not this store's question: it is asked of the `Document` that names it,
in the graph, before the store is asked for the bytes (rules 3 and 4).
"""

from __future__ import annotations

from typing import Protocol


class MediaNotFoundError(Exception):
    """No file is kept under this reference, or the reference is not one this store makes."""


class MediaStore(Protocol):
    async def put(self, data: bytes, content_type: str) -> str:
        """Keeps `data`; returns its reference, the same for the same bytes."""
        ...

    async def get(self, ref: str) -> bytes:
        """The bytes kept under `ref`; `MediaNotFoundError` if there are none."""
        ...
