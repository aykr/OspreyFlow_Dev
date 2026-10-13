"""The Conduit's media store, as the deployment names it (`05_DEPLOYMENT.md` §3a): S3 (Lite's
SeaweedFS, AWS's S3) unless `OSPREY_MEDIA_STORE=blob` (Azure). Any other name is refused in words —
a typo must not quietly keep files somewhere nobody backs up."""

from __future__ import annotations

import pytest
from adapters.media_blob import BlobMediaStore
from adapters.media_objectstore import ObjectStoreMediaStore
from services.api.media_store import open_media_store


def test_s3_unless_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSPREY_MEDIA_STORE", raising=False)
    assert isinstance(open_media_store(), ObjectStoreMediaStore)
    monkeypatch.setenv("OSPREY_MEDIA_STORE", "s3")
    assert isinstance(open_media_store(), ObjectStoreMediaStore)


def test_blob_when_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_MEDIA_STORE", "blob")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "ospreymedia1a2b")
    monkeypatch.setenv("AZURE_STORAGE_KEY", "a2V5")
    assert isinstance(open_media_store(), BlobMediaStore)


def test_another_name_is_refused_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_MEDIA_STORE", "azure")
    with pytest.raises(ValueError, match="OSPREY_MEDIA_STORE is `s3` or `blob`"):
        open_media_store()
