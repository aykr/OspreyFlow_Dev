"""Site image storage — `spec/00_ARCHITECTURE.md` §1.2's site-plan case,
`spec/02_GLASS_FRONTEND.md` §3.5, `08_ACCEPTANCE_SCENARIOS.md` A1.

Reuses `services/ingest/staging.py`'s `ObjectStorageConfig`/`filesystem`
directly rather than a second, near-identical dataclass — that class was
already fully generic (endpoint/credentials/bucket/TLS), so the only thing
this module needs of its own is a different bucket and the read/write
shape for one whole image file rather than a Parquet dataset. First
`UploadFile` caller in the Conduit; the browser never talks to the object
store directly, mirroring the tile proxy's own reasoning
(`00_ARCHITECTURE.md` §1.2 "The tile proxy") — credentials stay
server-side and every image read is a request the Conduit can audit.
"""

from __future__ import annotations

import os

from services.ingest.staging import ObjectStorageConfig, filesystem


def site_image_storage_config() -> ObjectStorageConfig:
    return ObjectStorageConfig(
        endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        bucket=os.environ.get("MINIO_SITE_IMAGES_BUCKET", "ospreyflow-site-images"),
        use_ssl=os.environ.get("MINIO_USE_SSL", "false").lower() == "true",
    )


def object_key_for(site_id: str) -> str:
    """One image per site, keyed on the site's own id — a re-upload
    (not offered by this checkpoint's UI, but not forbidden either)
    would simply overwrite it."""
    return f"sites/{site_id}/image"


def write_site_image(data: bytes, *, storage: ObjectStorageConfig, object_key: str) -> None:
    fs = filesystem(storage)
    fs.create_dir(storage.bucket)
    path = f"{storage.bucket}/{object_key}"
    with fs.open_output_stream(path) as sink:
        sink.write(data)


def read_site_image(*, storage: ObjectStorageConfig, object_key: str) -> bytes:
    fs = filesystem(storage)
    path = f"{storage.bucket}/{object_key}"
    with fs.open_input_file(path) as source:
        data: bytes = source.read()
    return data
