"""Every S3 client the deployment builds, on the server's own cloud identity (`05_DEPLOYMENT.md`
§3a, ADR-114 Amendment 10).

pyarrow uses the cloud's default credential chain — an EC2 instance role — only when it is given no
key at all: an empty string is sent as a key. So `MINIO_CREDENTIALS=instance` must reach each client
as `None`, with the region the bucket lives in; and without it, Lite's keys must still be sent as
they are. Checked at each real call site, through the settings pyarrow itself reports.
"""

from __future__ import annotations

from typing import Any

import pytest
from adapters.media_objectstore import MediaStoreConfig, ObjectStoreMediaStore
from services.api.object_transfer import store_from_env
from services.api.site_images import site_image_storage_config
from services.api.tile_cache import tile_cache_storage_config
from services.ingest.staging import ObjectStorageConfig, filesystem


def _settings(store: Any) -> dict[str, Any]:
    return store.__reduce__()[1][0]  # type: ignore[no-any-return]


def _every_client() -> dict[str, Any]:
    return {
        "media": ObjectStoreMediaStore(MediaStoreConfig.from_env())._fs,
        "staging": filesystem(ObjectStorageConfig.from_env()),
        "site images": filesystem(site_image_storage_config()),
        "tile cache": filesystem(tile_cache_storage_config()),
        "backup transfer": store_from_env(),
    }


def test_on_an_instance_role_no_client_sends_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_CREDENTIALS", "instance")
    monkeypatch.setenv("MINIO_ENDPOINT", "s3.eu-west-2.amazonaws.com")
    monkeypatch.setenv("MINIO_REGION", "eu-west-2")
    monkeypatch.setenv("MINIO_USE_SSL", "true")
    # A key left over in the environment must not win over the role.
    monkeypatch.setenv("MINIO_ACCESS_KEY", "left-over")
    monkeypatch.setenv("MINIO_SECRET_KEY", "left-over")
    for name, client in _every_client().items():
        settings = _settings(client)
        assert (settings["access_key"], settings["secret_key"]) == (None, None), name
        assert settings["region"] == "eu-west-2", name
        assert settings["scheme"] == "https", name


def test_with_keys_every_client_sends_them_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINIO_CREDENTIALS", raising=False)
    monkeypatch.delenv("MINIO_REGION", raising=False)
    monkeypatch.setenv("MINIO_ACCESS_KEY", "ospreyflow")
    monkeypatch.setenv("MINIO_SECRET_KEY", "s3cret")
    for name, client in _every_client().items():
        settings = _settings(client)
        assert (settings["access_key"], settings["secret_key"]) == ("ospreyflow", "s3cret"), name


def test_an_unknown_credentials_setting_is_refused_in_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINIO_CREDENTIALS", "role")
    with pytest.raises(ValueError, match="MINIO_CREDENTIALS is `keys` or `instance`"):
        _every_client()


def test_bucket_names_take_the_deployments_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """S3 bucket names are global: a cloud deployment's are `<prefix><name>`, as OpenTofu made them."""
    monkeypatch.setenv("MINIO_BUCKET_PREFIX", "osprey-small-1a2b-")
    assert MediaStoreConfig.from_env().bucket == "osprey-small-1a2b-media"
    assert ObjectStorageConfig.from_env().bucket == "osprey-small-1a2b-staging"
    assert site_image_storage_config().bucket == "osprey-small-1a2b-site-images"
    assert tile_cache_storage_config().bucket == "osprey-small-1a2b-tile-cache"
    monkeypatch.delenv("MINIO_BUCKET_PREFIX")
    assert MediaStoreConfig.from_env().bucket == "ospreyflow-media"
