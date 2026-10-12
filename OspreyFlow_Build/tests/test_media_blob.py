"""The Blob media adapter's own claims beyond the `MediaStore` suite (ADR-114 decision 8): the
Shared Key signature is the one the service checks, so a wrong key is refused by the service —
measured against Azurite, which refuses it as Azure does — and a refusal is said, never taken for
"not found"."""

from __future__ import annotations

import base64

import pytest

from adapters.media_blob import BlobMediaStore, BlobStoreConfig, BlobStoreError, string_to_sign
from adapters.media_blob.testing import blob_media_store

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic image bytes"


def test_the_blob_adapter_is_in_the_media_store_suite_wherever_this_file_runs() -> None:
    """This file runs only where a Blob service is configured; the suite must run there too."""
    from tests.conformance.registry import MEDIA_STORE_ADAPTERS

    assert "media_blob" in [str(f) for f in MEDIA_STORE_ADAPTERS]


def test_the_string_to_sign_names_the_account_path_query_and_ms_headers_in_order() -> None:
    text = string_to_sign(
        "PUT",
        "http://127.0.0.1:10000/acct/media-x?restype=container&Comp=list",
        {"x-ms-version": "v", "x-ms-date": "d", "content-type": "image/png"},
        "acct",
        5,
    )
    lines = text.split("\n")
    assert lines[0] == "PUT" and lines[3] == "5" and lines[5] == "image/png"
    assert "x-ms-date:d\nx-ms-version:v\n/acct/acct/media-x\ncomp:list\nrestype:container" in text


async def test_a_wrong_key_is_refused_by_the_service_not_read_as_missing() -> None:
    async with blob_media_store() as good:
        ref = await good.put(PNG, "image/png")
        config = good._config  # noqa: SLF001 — the same container, a different key
    wrong = BlobMediaStore(
        BlobStoreConfig(
            account=config.account,
            key=base64.b64encode(b"not the account key at all").decode(),
            container=config.container,
            endpoint=config.endpoint,
        )
    )
    try:
        with pytest.raises(BlobStoreError, match="403"):
            await wrong.get(ref)
        with pytest.raises(BlobStoreError, match="403"):
            await wrong.put(PNG + b"!", "image/png")
    finally:
        await wrong.aclose()


@pytest.mark.parametrize("planted", ["other/a.png", "media/ABC.png"])
async def test_a_blob_held_under_a_name_the_store_does_not_make_is_refused(planted: str) -> None:
    """Rule 15: the blob is really there, so only the reference check can refuse it."""
    from ports.media import MediaNotFoundError

    async with blob_media_store() as store:
        await store.put(PNG, "image/png")  # makes the container
        made = await store._send(  # noqa: SLF001 — writing past the store's own naming
            "PUT",
            store._url(planted),  # noqa: SLF001
            content=b"present",
            headers={"x-ms-blob-type": "BlockBlob", "content-type": "image/png"},
        )
        assert made.status_code == 201
        with pytest.raises(MediaNotFoundError):
            await store.get(planted)
