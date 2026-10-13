"""The object store's contents as plain files, and back (ADR-114 Amendment 9 point 3a).

Backup, restore and the move from MinIO to SeaweedFS all go through S3 — never a store's private
data folder, which no other store can read. Every object is written as `objects/<bucket>/<key>`
beside `manifest.json` (every bucket, empty ones too; each object's size and SHA-256), and an import
checks every file against the manifest before writing anything, then reads each object back.

It runs in the Conduit's image, inside the deployment's network, with the deployment's own
`MINIO_*` settings:

    python -m services.api.object_transfer export /out
    python -m services.api.object_transfer import /in
    python -m services.api.object_transfer manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyarrow import fs

FORMAT = 1
_CHUNK = 1 << 20


class TransferRefused(Exception):
    """A transfer that may not go on, and why."""


def store_from_env(*, allow_bucket_deletion: bool = False) -> fs.S3FileSystem:
    secure = os.environ.get("MINIO_USE_SSL", "false").lower() == "true"
    return fs.S3FileSystem(
        endpoint_override=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        scheme="https" if secure else "http",
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        region=os.environ.get("MINIO_REGION", "us-east-1"),
        allow_bucket_creation=True,
        allow_bucket_deletion=allow_bucket_deletion,
    )


def _refused(error: OSError) -> TransferRefused:
    said = str(error)
    markers = ("ACCESS_DENIED", "403", "SIGNATURE_DOES_NOT_MATCH", "SignatureDoesNotMatch",
               "INVALID_ACCESS_KEY", "InvalidAccessKeyId")  # fmt: skip
    if any(marker in said for marker in markers):
        return TransferRefused(f"the object store refused these credentials ({said[:160]})")
    return TransferRefused(f"the object store could not answer ({said[:160]})")


def _buckets(store: fs.S3FileSystem, only: Sequence[str] | None) -> list[str]:
    if only is not None:
        return list(only)
    try:
        listed = store.get_file_info(fs.FileSelector("", recursive=False))
    except OSError as error:
        raise _refused(error) from None
    return sorted(i.path for i in listed if i.type == fs.FileType.Directory)


def _files(store: fs.S3FileSystem, bucket: str) -> list[fs.FileInfo]:
    try:
        listed = store.get_file_info(fs.FileSelector(bucket, recursive=True, allow_not_found=True))
    except OSError as error:
        raise _refused(error) from None
    return sorted((i for i in listed if i.type == fs.FileType.File), key=lambda i: i.path)


def _sha256(stream: Any) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    while chunk := stream.read(_CHUNK):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def manifest_of(store: fs.S3FileSystem, *, buckets: Sequence[str] | None = None) -> dict[str, Any]:
    """What the store holds now: its buckets and each object's size and SHA-256."""
    names = _buckets(store, buckets)
    objects = []
    for bucket in names:
        for info in _files(store, bucket):
            with store.open_input_stream(info.path) as stream:
                sha, size = _sha256(stream)
            objects.append({"bucket": bucket, "key": info.path[len(bucket) + 1 :], "size": size,
                            "sha256": sha})  # fmt: skip
    present = [b for b in names if store.get_file_info(b).type == fs.FileType.Directory]
    return {"format": FORMAT, "buckets": present, "objects": objects}


def export_objects(
    store: fs.S3FileSystem, out: Path, *, buckets: Sequence[str] | None = None
) -> dict[str, Any]:
    """Every object into `out/objects/<bucket>/<key>`, and `out/manifest.json`."""
    names = _buckets(store, buckets)
    objects = []
    for bucket in names:
        for info in _files(store, bucket):
            key = info.path[len(bucket) + 1 :]
            target = out / "objects" / bucket / key
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with store.open_input_stream(info.path) as stream, target.open("wb") as file:
                while chunk := stream.read(_CHUNK):
                    file.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            objects.append({"bucket": bucket, "key": key, "size": size,
                            "sha256": digest.hexdigest()})  # fmt: skip
    manifest = {"format": FORMAT, "buckets": names, "objects": objects}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def import_objects(store: fs.S3FileSystem, src: Path) -> int:
    """Every file of an export written back, after all of them are checked against the manifest;
    each object then read back and compared. Returns how many objects were written."""
    try:
        manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as unreadable:
        raise TransferRefused(f"{src} holds no readable manifest.json ({unreadable})") from None
    if manifest.get("format") != FORMAT:
        raise TransferRefused(f"{src} is an export of another format ({manifest.get('format')})")
    for item in manifest["objects"]:
        path = src / "objects" / item["bucket"] / item["key"]
        try:
            with path.open("rb") as file:
                sha, size = _sha256(file)
        except OSError:
            raise TransferRefused(f"{item['bucket']}/{item['key']} is missing from {src}") from None
        if (sha, size) != (item["sha256"], item["size"]):
            raise TransferRefused(
                f"{item['bucket']}/{item['key']} does not match its manifest entry; nothing was "
                "written"
            )
    try:
        for bucket in manifest["buckets"]:
            store.create_dir(bucket)
        for item in manifest["objects"]:
            path = f"{item['bucket']}/{item['key']}"
            with (src / "objects" / item["bucket"] / item["key"]).open("rb") as file, \
                    store.open_output_stream(path) as out:  # fmt: skip
                while chunk := file.read(_CHUNK):
                    out.write(chunk)
            with store.open_input_stream(path) as stream:
                if _sha256(stream)[0] != item["sha256"]:
                    raise TransferRefused(f"{path} reads back other than it was written")
    except OSError as error:
        raise _refused(error) from None
    return len(manifest["objects"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="object_transfer", description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    exporting = sub.add_parser("export")
    exporting.add_argument("out", type=Path)
    importing = sub.add_parser("import")
    importing.add_argument("src", type=Path)
    sub.add_parser("manifest")
    args = parser.parse_args(argv)
    store = store_from_env()
    try:
        if args.action == "export":
            args.out.mkdir(parents=True, exist_ok=True)
            manifest = export_objects(store, args.out)
            print(f"exported {len(manifest['objects'])} object(s) in "
                  f"{len(manifest['buckets'])} bucket(s)")  # fmt: skip
        elif args.action == "import":
            print(f"imported {import_objects(store, args.src)} object(s)")
        else:
            print(json.dumps(manifest_of(store), indent=1))
    except TransferRefused as refused:
        print(f"object_transfer: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
