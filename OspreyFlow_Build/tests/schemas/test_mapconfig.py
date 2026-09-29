"""The basemap provider registry — `spec/00_ARCHITECTURE.md` §1.2."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.mapconfig import (
    ClientScope,
    MapConfig,
    MapProvider,
    MapSourceKind,
    OgcServiceKind,
    PrefetchCache,
    ProviderLicence,
)


def _licence(**overrides: object) -> ProviderLicence:
    base: dict[str, object] = {"id": "ODbL", "redistributable": True, "client_scope": "open"}
    base.update(overrides)
    return ProviderLicence.model_validate(base)


def _provider(**overrides: object) -> MapProvider:
    base: dict[str, object] = {
        "id": "osm-local",
        "label": "OpenStreetMap",
        "kind": "vector",
        "source": "file:///data/tiles/gb-osm.pmtiles",
        "style": "bundled:osprey-dark",
        "attribution": "© OpenStreetMap contributors",
        "licence": _licence(),
    }
    base.update(overrides)
    return MapProvider.model_validate(base)


def test_tier_1_provider_round_trips() -> None:
    provider = _provider()
    assert provider.kind is MapSourceKind.VECTOR
    assert provider.licence.client_scope is ClientScope.OPEN


def test_a_provider_must_declare_exactly_one_resolution_path() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        _provider(source=None)  # neither source, service+endpoint, nor profile
    with pytest.raises(ValidationError, match="exactly one"):
        _provider(profile="esri-arcgis-online")  # source AND profile both set


def test_a_tier_4_provider_needs_both_service_and_endpoint() -> None:
    with pytest.raises(ValidationError, match="declares service but not endpoint"):
        _provider(source=None, service=OgcServiceKind.WMTS)


def test_a_tier_4_provider_with_service_and_endpoint_is_valid() -> None:
    provider = _provider(
        source=None, kind="raster", service="wmts", endpoint="https://gis.internal/wmts",
        layer="aerial:latest",
    )
    assert provider.service is OgcServiceKind.WMTS


def test_credential_must_be_an_env_reference_not_a_literal_value() -> None:
    with pytest.raises(ValidationError, match="env:VAR_NAME"):
        _provider(credential="sk-abc123")
    provider = _provider(credential="env:OS_DATAHUB_API_KEY")
    assert provider.credential == "env:OS_DATAHUB_API_KEY"


def test_prefetch_cache_is_optional_and_only_meaningful_for_tier_3() -> None:
    provider = _provider(cache=PrefetchCache(ttl_days=30, prefetch_areas=["area-of-operations"]))
    assert provider.cache is not None
    assert provider.cache.ttl_days == 30


def test_map_config_requires_the_default_to_be_a_declared_provider() -> None:
    with pytest.raises(ValidationError, match="not a declared provider"):
        MapConfig(default="does-not-exist", providers=[_provider()])


def test_map_config_rejects_duplicate_provider_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        MapConfig(default="osm-local", providers=[_provider(), _provider()])


def test_map_config_accepts_a_single_tier_1_provider() -> None:
    config = MapConfig(default="osm-local", providers=[_provider()])
    assert config.default == "osm-local"
    assert len(config.providers) == 1


def test_a_provider_with_a_blank_id_is_refused() -> None:
    """Seen: the Admin console saved `osprey.yaml` with `id: ''` and `default: ''`. Those two agree
    with each other, so the consistency check let them through and the map went blank."""
    with pytest.raises(ValidationError):
        _provider(id="")


def test_a_blank_default_is_refused_even_when_a_blank_id_would_match_it() -> None:
    with pytest.raises(ValidationError):
        MapConfig.model_validate(
            {
                "default": "",
                "providers": [_provider().model_dump(mode="json") | {"id": ""}],
            }
        )
