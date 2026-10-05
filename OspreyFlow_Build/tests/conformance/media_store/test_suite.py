"""`MediaStore` conformance suite (ADR-094 step 2). Written before the adapters (rule 1).

Parametrised over `MEDIA_STORE_ADAPTERS`. The object-store adapter needs an S3-compatible store
(MinIO) at `MINIO_ENDPOINT`, as the ingest staging tests do.
"""

from __future__ import annotations

import pytest

from ports.media import MediaNotFoundError
from tests.conformance.registry import MEDIA_STORE_ADAPTERS, MediaStoreFactory

pytestmark = pytest.mark.parametrize("factory", MEDIA_STORE_ADAPTERS, ids=str)

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic image bytes"


async def test_a_file_put_comes_back_whole(factory: MediaStoreFactory) -> None:
    async with factory.context() as store:
        ref = await store.put(PNG, "image/png")
        assert await store.get(ref) == PNG


async def test_the_same_bytes_get_the_same_reference_and_different_bytes_another(
    factory: MediaStoreFactory,
) -> None:
    async with factory.context() as store:
        first = await store.put(PNG, "image/png")
        again = await store.put(PNG, "image/png")
        other = await store.put(PNG + b"!", "image/png")
        assert first == again != other


async def test_a_reference_says_what_kind_of_file_it_names(factory: MediaStoreFactory) -> None:
    async with factory.context() as store:
        assert (await store.put(PNG, "image/png")).endswith(".png")
        assert (await store.put(b"text", "text/plain")).endswith(".txt")
        assert (await store.put(b"\x00\x00\x00\x18ftypmp42", "video/mp4")).endswith(".mp4")


async def test_a_reference_never_put_is_not_found(factory: MediaStoreFactory) -> None:
    async with factory.context() as store:
        with pytest.raises(MediaNotFoundError):
            await store.get("media/" + "0" * 64 + ".png")


@pytest.mark.parametrize(
    "ref", ["../etc/passwd", "/etc/passwd", "media/../../x.png", "", "other/a.png"]
)
async def test_a_reference_this_store_does_not_make_is_not_found(
    factory: MediaStoreFactory, ref: str
) -> None:
    """Not a path: a reference that would reach outside the store's own names is refused as
    missing, before anything is read."""
    async with factory.context() as store:
        with pytest.raises(MediaNotFoundError):
            await store.get(ref)
