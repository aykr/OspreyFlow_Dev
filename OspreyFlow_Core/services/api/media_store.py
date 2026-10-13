"""Which media store the Conduit keeps content files in (ADR-094; `05_DEPLOYMENT.md` §3a): the
S3-protocol store unless the deployment names Blob, Azure's, with `OSPREY_MEDIA_STORE=blob`."""

from __future__ import annotations

import os

from adapters.media_blob import BlobMediaStore, BlobStoreConfig
from adapters.media_objectstore import MediaStoreConfig, ObjectStoreMediaStore
from ports.media import MediaStore


def open_media_store() -> MediaStore:
    named = os.environ.get("OSPREY_MEDIA_STORE", "s3")
    if named == "s3":
        return ObjectStoreMediaStore(MediaStoreConfig.from_env())
    if named == "blob":
        return BlobMediaStore(BlobStoreConfig.from_env())
    raise ValueError(f"OSPREY_MEDIA_STORE is `s3` or `blob`, not {named!r}")
