"""`services/api/tile_proxy.py` — `docs/00_ARCHITECTURE.md` §1.2's tile
proxy, `docs/07_BUILD_PLAN.md` Phase 5 Checkpoint 3b, Phase 5's known-gaps
closure's WMTS KVP fix for the `MapProvider.endpoint` conflict Checkpoint
3b/3c left open."""

from __future__ import annotations

import pytest
from services.api.credentials import MissingCredentialError
from services.api.tile_proxy import build_upstream_url, fetch_tile

from schemas.mapconfig import MapProvider


def _template_provider(**overrides: object) -> MapProvider:
    """A tier 1-3-shaped provider resolved via a `source` template —
    `build_upstream_url`'s original template-substitution path, unchanged
    by the WMTS KVP fix (that fix only touches `service: wmts` providers)."""
    base: dict[str, object] = {
        "id": "tier3-hosted",
        "label": "A hosted tier-3 source",
        "kind": "raster",
        "source": "https://basemap.example.test/{layer}/{z}/{y}/{x}",
        "variables": {"layer": "USGSTopo"},
        "proxy": "recommended",
        "attribution": "Example",
        "licence": {"id": "example", "redistributable": True, "client_scope": "open"},
    }
    base.update(overrides)
    return MapProvider.model_validate(base)


def _wmts_provider(**overrides: object) -> MapProvider:
    """A tier-4 WMTS provider: `endpoint` is always a bare service base
    URL (never a `{z}`/`{x}`/`{y}` template) — the corrected, single
    contract `tier4_registration.py`/`verify_map.py` already used, and
    `build_upstream_url` now agrees with."""
    base: dict[str, object] = {
        "id": "usgs-national-map",
        "label": "USGS The National Map",
        "kind": "raster",
        "service": "wmts",
        "endpoint": "https://basemap.nationalmap.gov/arcgis/rest/services/wmts",
        "layer": "USGSTopo",
        "tile_matrix_set": "GoogleMapsCompatible",
        "format": "image/png",
        "wmts_style": "default",
        "proxy": "recommended",
        "attribution": "USGS The National Map",
        "licence": {"id": "usgs-public-domain", "redistributable": True, "client_scope": "open"},
    }
    base.update(overrides)
    return MapProvider.model_validate(base)


def test_builds_a_wmts_kvp_get_tile_url() -> None:
    provider = _wmts_provider()

    url = build_upstream_url(provider, z=5, x=10, y=15)

    assert url == (
        "https://basemap.nationalmap.gov/arcgis/rest/services/wmts"
        "?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=USGSTopo&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible"
        "&TILEMATRIX=5&TILEROW=15&TILECOL=10&FORMAT=image/png"
    )


def test_wmts_kvp_url_carries_extra_variables_as_query_parameters() -> None:
    provider = _wmts_provider(variables={"api_version": "2"})

    url = build_upstream_url(provider, z=0, x=0, y=0)

    assert url.endswith("&api_version=2")


@pytest.mark.parametrize(
    "missing_field", ["layer", "tile_matrix_set", "format", "wmts_style"]
)
def test_wmts_raises_naming_a_missing_discovered_field(missing_field: str) -> None:
    provider = _wmts_provider(**{missing_field: None})

    with pytest.raises(ValueError, match=missing_field):
        build_upstream_url(provider, z=0, x=0, y=0)


def test_wmts_with_a_credential_is_not_yet_supported() -> None:
    """Flagged, not guessed — see `_build_wmts_kvp_url`'s own docstring:
    no shipped or tested provider needs a credentialed WMTS KVP request
    yet, and there is no declared query-parameter name for one."""
    provider = _wmts_provider(credential="env:SOME_KEY")

    with pytest.raises(NotImplementedError):
        build_upstream_url(provider, z=0, x=0, y=0)


def test_substitutes_z_x_y_and_declared_variables() -> None:
    provider = _template_provider()

    url = build_upstream_url(provider, z=5, x=10, y=15)

    assert url == "https://basemap.example.test/USGSTopo/5/15/10"


def test_substitutes_a_resolved_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_WMTS_KEY", "topsecret")
    provider = _template_provider(
        source="http://127.0.0.1:9/wmts/{z}/{x}/{y}?key={credential}",
        credential="env:LOCAL_WMTS_KEY",
        proxy="required",
    )

    url = build_upstream_url(provider, z=1, x=2, y=3)

    assert url == "http://127.0.0.1:9/wmts/1/2/3?key=topsecret"


def test_raises_naming_the_variable_when_credential_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_WMTS_KEY", raising=False)
    provider = _template_provider(
        source="http://127.0.0.1:9/wmts/{z}/{x}/{y}?key={credential}",
        credential="env:LOCAL_WMTS_KEY",
        proxy="required",
    )

    with pytest.raises(MissingCredentialError):
        build_upstream_url(provider, z=1, x=2, y=3)


def test_a_provider_with_neither_endpoint_nor_source_is_rejected() -> None:
    provider = _template_provider(source=None, service=None, endpoint=None, profile="some-profile")

    with pytest.raises(ValueError, match="no endpoint or source"):
        build_upstream_url(provider, z=0, x=0, y=0)


async def test_fetch_tile_calls_the_injected_http_get_with_the_built_url() -> None:
    calls: list[str] = []

    async def fake_http_get(url: str) -> bytes:
        calls.append(url)
        return b"fake-tile-bytes"

    result = await fetch_tile("https://example.test/tile", http_get=fake_http_get)

    assert result == b"fake-tile-bytes"
    assert calls == ["https://example.test/tile"]
