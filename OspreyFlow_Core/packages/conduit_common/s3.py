"""How every S3 client in the deployment reads its connection (`05_DEPLOYMENT.md` §3a).

One place, so the media store, ingest staging, site images, the tile cache and the backup transfer
cannot disagree about it:

- `MINIO_CREDENTIALS` is `keys` (the default: `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`, as Lite's
  SeaweedFS takes) or `instance` — the server's own cloud identity, an EC2 instance role. pyarrow
  uses the cloud's credential chain only when it is given no key at all (an empty string is sent as
  a key), so `instance` gives `None`, whatever else is in the environment.
- `MINIO_REGION`, the region the buckets live in, when set.
- `MINIO_BUCKET_PREFIX`: a cloud's bucket names are global, so a deployment's are `<prefix><name>`,
  as OpenTofu made them; `ospreyflow-` by default. A bucket's own variable still wins.
"""

from __future__ import annotations

import os

_DEFAULT_KEY = "minioadmin"


def s3_keys() -> tuple[str | None, str | None]:
    credentials = os.environ.get("MINIO_CREDENTIALS", "keys")
    if credentials == "instance":
        return None, None
    if credentials != "keys":
        raise ValueError(
            f"MINIO_CREDENTIALS is `keys` or `instance` (the server's own cloud identity), "
            f"not {credentials!r}"
        )
    return (
        os.environ.get("MINIO_ACCESS_KEY", _DEFAULT_KEY),
        os.environ.get("MINIO_SECRET_KEY", _DEFAULT_KEY),
    )


def s3_region() -> str | None:
    return os.environ.get("MINIO_REGION") or None


def s3_bucket(variable: str, name: str) -> str:
    prefix = os.environ.get("MINIO_BUCKET_PREFIX", "ospreyflow-")
    return os.environ.get(variable) or f"{prefix}{name}"
