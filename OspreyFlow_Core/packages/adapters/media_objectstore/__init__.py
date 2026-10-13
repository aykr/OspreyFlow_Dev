"""`MediaStore` over the deployment's S3-compatible object store (MinIO), ADR-094 step 2.

A reference is `media/<sha256 of the bytes>.<extension for the content type>`: content-addressed,
so the same file is kept once, and a name this store did not make (any other shape, a path, a
parent step) is refused as missing before anything is read. The bucket is the deployment's media
bucket, separate from ingest staging.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass

import pyarrow.fs as pa_fs

from conduit_common.s3 import s3_bucket, s3_keys, s3_region
from ports.media import MediaNotFoundError

#: The extension a reference carries for each content type the Studio and the reader handle.
EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/tiff": "tif",
    "image/heic": "heic",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "text/plain": "txt",
    "application/pdf": "pdf",
}
CONTENT_TYPES = {ext: content_type for content_type, ext in EXTENSIONS.items()}

_REF = re.compile(r"^media/[0-9a-f]{64}\.([a-z0-9]{1,5})$")


def reference_for(data: bytes, content_type: str) -> str:
    ext = EXTENSIONS.get(content_type, "bin")
    return f"media/{hashlib.sha256(data).hexdigest()}.{ext}"


def checked(ref: str) -> str:
    """`ref` if it is a name this store makes; otherwise `MediaNotFoundError`."""
    if not _REF.match(ref):
        raise MediaNotFoundError(ref)
    return ref


def content_type_of(ref: str) -> str:
    match = _REF.match(ref)
    return CONTENT_TYPES.get(match.group(1), "application/octet-stream") if match else ""


@dataclass(frozen=True)
class MediaStoreConfig:
    endpoint: str = "localhost:9000"
    #: `None` for both: the server's own cloud identity (`conduit_common.s3`).
    access_key: str | None = "minioadmin"
    secret_key: str | None = "minioadmin"
    bucket: str = "ospreyflow-media"
    use_ssl: bool = False
    region: str | None = None

    @classmethod
    def from_env(cls) -> MediaStoreConfig:
        """Read as every S3 client reads its own (`conduit_common.s3`)."""
        access_key, secret_key = s3_keys()
        return cls(
            endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
            access_key=access_key,
            secret_key=secret_key,
            bucket=s3_bucket("MINIO_MEDIA_BUCKET", "media"),
            use_ssl=os.environ.get("MINIO_USE_SSL", "false").lower() == "true",
            region=s3_region(),
        )


class ObjectStoreMediaStore:
    def __init__(self, config: MediaStoreConfig) -> None:
        self._config = config
        self._fs = pa_fs.S3FileSystem(
            endpoint_override=config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            scheme="https" if config.use_ssl else "http",
            region=config.region,
            # As ingest staging does: the media bucket is made on first use, so a fresh deployment
            # needs no separate provisioning step.
            allow_bucket_creation=True,
        )
        self._bucket_ready = False

    def _path(self, ref: str) -> str:
        return f"{self._config.bucket}/{ref}"

    def _ensure_bucket(self) -> None:
        if not self._bucket_ready:
            self._fs.create_dir(self._config.bucket, recursive=True)
            self._bucket_ready = True

    def _put(self, data: bytes, ref: str) -> None:
        self._ensure_bucket()
        with self._fs.open_output_stream(self._path(ref)) as out:
            out.write(data)

    def _get(self, ref: str) -> bytes:
        try:
            with self._fs.open_input_stream(self._path(ref)) as handle:
                return bytes(handle.read())
        except (FileNotFoundError, OSError) as error:
            raise MediaNotFoundError(ref) from error

    async def put(self, data: bytes, content_type: str) -> str:
        ref = reference_for(data, content_type)
        await asyncio.to_thread(self._put, data, ref)
        return ref

    async def get(self, ref: str) -> bytes:
        return await asyncio.to_thread(self._get, checked(ref))
