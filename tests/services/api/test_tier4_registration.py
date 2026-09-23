"""`services/api/tier4_registration.py` — `docs/00_ARCHITECTURE.md` §1.2's
"Capabilities documents are parsed at registration" and §1.2.2's CRS
refusal. Against synthetic,
in-repo capabilities documents (rule 9) — no real USGS/OS Data Hub
capabilities XML fetched or copied in.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from services.api.tier4_registration import (
    DiscoveredCapabilities,
    UnsupportedProjectionError,
    parse_wmts_capabilities,
    register_tier4_provider,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "wmts_capabilities"


def test_parses_layers_projection_and_zoom_range_from_a_valid_document() -> None:
    xml_bytes = (FIXTURES / "usgs_national_map_valid.xml").read_bytes()

    result = parse_wmts_capabilities(xml_bytes)

    assert result == DiscoveredCapabilities(
        layers=("USGSTopo", "USGSImageryOnly", "USGSShadedReliefOnly", "USGSHydroCached"),
        projection="EPSG:3857",
        zoom_min=0,
        zoom_max=16,
        tile_matrix_set="GoogleMapsCompatible",
        format="image/png",
        style="default",
    )


def test_refuses_a_service_offering_neither_wgs84_nor_web_mercator() -> None:
    xml_bytes = (FIXTURES / "unsupported_crs.xml").read_bytes()

    with pytest.raises(UnsupportedProjectionError) as exc_info:
        parse_wmts_capabilities(xml_bytes)

    assert exc_info.value.declared_crs == "EPSG:27700"


def test_refuses_a_document_whose_first_layer_declares_no_format() -> None:
    xml_bytes = (FIXTURES / "missing_format.xml").read_bytes()

    with pytest.raises(ValueError, match="declares no Format"):
        parse_wmts_capabilities(xml_bytes)


def test_refuses_a_document_whose_first_layer_declares_no_style() -> None:
    xml_bytes = (FIXTURES / "missing_style.xml").read_bytes()

    with pytest.raises(ValueError, match="declares no Style"):
        parse_wmts_capabilities(xml_bytes)


async def test_register_tier4_provider_requests_get_capabilities_and_parses_the_result() -> None:
    xml_bytes = (FIXTURES / "usgs_national_map_valid.xml").read_bytes()
    requested_urls: list[str] = []

    async def fake_http_get(url: str) -> bytes:
        requested_urls.append(url)
        return xml_bytes

    result = await register_tier4_provider(
        "https://basemap.nationalmap.gov/arcgis/rest/services/wmts", http_get=fake_http_get
    )

    assert requested_urls == [
        "https://basemap.nationalmap.gov/arcgis/rest/services/wmts"
        "?SERVICE=WMTS&REQUEST=GetCapabilities"
    ]
    assert result.projection == "EPSG:3857"
    assert result.zoom_max == 16
