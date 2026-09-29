"""Tier-4 WMTS capabilities parsing and CRS gate — `spec/00_ARCHITECTURE.md`
§1.2 ("Capabilities documents are parsed at registration") and §1.2.2 (the
CRS refusal: "`osprey map add` reads it and refuses a service that offers
neither WGS84 nor Web Mercator rather than registering something that
will misplace data later").

**Scoped to WMTS only this checkpoint** — no shipped profile
(`providers/os-open-zoomstack.yaml`'s `service: mvt`, `providers/
usgs-national-map.yaml`'s `service: wmts`) needs WMS/WFS/OGC-Features
parsing yet, and WFS/OGC-Features capabilities describe *feature types*
for entity creation (a gazetteer-connector-shaped concern) rather than
zoom/tile parameters. The same mechanism would extend to those formats
later — flagged as a real, separate piece of work, not silently assumed
covered.

Parses via `defusedxml.ElementTree`, never stdlib `xml.etree` — a WMTS
capabilities document is untrusted, network-fetched, deployer-configured
XML, and stdlib `ElementTree` is vulnerable to XXE/billion-laughs against
exactly that kind of input.

**`register_tier4_provider` expects `endpoint` to be a bare WMTS base
URL** (`?SERVICE=WMTS&REQUEST=GetCapabilities` is appended here) —
`services/api/tile_proxy.py`'s `build_upstream_url` now agrees: `endpoint`
is always this bare shape, and `build_upstream_url` builds a real WMTS KVP
`GetTile` request from it rather than requiring a `{z}`/`{x}`/`{y}`-templated
`endpoint` (the conflict this module's docstring used to record here is
closed, Phase 5's known-gaps closure). `tile_matrix_set`/`format`/`style` are discovered here
for exactly that KVP request, alongside the zoom range and projection
already discovered — a deployer copies all of them into `osprey.yaml`'s
`MapProvider` entry the same way `layer` is already hand-copied.

Discovered from the *first* `Layer` element's own `Style`/`Format`
children — correct for a single-style/single-format WMTS deployment (the
common case, and the only shape either shipped profile or the corporate
worked example needs); a per-layer generalisation, where different layers
of the same service declare different styles or formats, is real,
separate work, not silently assumed general.

Zoom range is read off `TileMatrix`/`Identifier` values directly, which is
correct for the common `GoogleMapsCompatible` tile matrix set (both
Checkpoint 3a profiles use it) where identifiers are literally the zoom
level numbers. A generic scale-denominator-based mapping for an arbitrary
tile matrix set is real, separate work — flagged, not silently assumed
general. No `osprey map add` CLI exists (this phase's standing "no CLI
yet" position) — `register_tier4_provider` is a plain callable;
`scripts/register_tier4_provider.py` is its CLI-equivalent wrapper.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from xml.etree.ElementTree import Element

import httpx
from defusedxml import ElementTree as DefusedET

SUPPORTED_CRS = {"EPSG:4326", "EPSG:3857"}


class UnsupportedProjectionError(RuntimeError):
    def __init__(self, declared_crs: str) -> None:
        self.declared_crs = declared_crs
        super().__init__(
            f"capabilities document declares {declared_crs!r}, which is neither "
            "WGS84 (EPSG:4326) nor Web Mercator (EPSG:3857)"
        )


@dataclass(frozen=True)
class DiscoveredCapabilities:
    layers: tuple[str, ...]
    projection: str
    zoom_min: int
    zoom_max: int
    #: WMTS KVP `GetTile` parameters `tile_proxy.build_upstream_url` needs —
    #: see this module's own docstring for why they're read off the first
    #: `Layer` only.
    tile_matrix_set: str
    format: str
    style: str


def _local_name(tag: str) -> str:
    """Strips a `{namespace}` prefix — capabilities documents in the wild
    vary in namespace prefix conventions; matching on the local tag name
    is robust to that without a namespace map for every real WMTS
    server's own XML declaration."""
    return tag.rsplit("}", 1)[-1]


def _find_all_local(root: Element, name: str) -> list[Element]:
    return [el for el in root.iter() if _local_name(el.tag) == name]


def _text_of_local(el: Element, name: str) -> str | None:
    for child in el:
        if _local_name(child.tag) == name:
            return child.text
    return None


def _normalise_crs(raw: str) -> str:
    """`SupportedCRS` is usually a URN (`urn:ogc:def:crs:EPSG::3857`), not
    a bare `EPSG:3857` — the numeric EPSG code is always the final
    colon-separated segment."""
    parts = [p for p in raw.split(":") if p]
    return f"EPSG:{parts[-1]}"


def _first_local_child(el: Element, name: str) -> Element | None:
    for child in el:
        if _local_name(child.tag) == name:
            return child
    return None


def parse_wmts_capabilities(xml_bytes: bytes) -> DiscoveredCapabilities:
    root = DefusedET.fromstring(xml_bytes)

    layers = _find_all_local(root, "Layer")
    layer_names = tuple(
        name for name in (_text_of_local(layer, "Identifier") for layer in layers) if name
    )
    if not layers:
        raise ValueError("capabilities document declares no Layer")

    # `_find_all_local(root, "TileMatrixSet")` also matches each Layer's
    # own `TileMatrixSetLink/TileMatrixSet` — a bare-text *reference* to a
    # tile matrix set by name, not its definition. The real definition
    # (direct child of `Contents`) is the one that itself has `TileMatrix`
    # children; a reference element never does.
    tile_matrix_sets = [
        el for el in _find_all_local(root, "TileMatrixSet") if _find_all_local(el, "TileMatrix")
    ]
    if not tile_matrix_sets:
        raise ValueError("capabilities document declares no TileMatrixSet")
    tile_matrix_set = tile_matrix_sets[0]

    supported_crs_raw = _text_of_local(tile_matrix_set, "SupportedCRS")
    if supported_crs_raw is None:
        raise ValueError("TileMatrixSet declares no SupportedCRS")
    projection = _normalise_crs(supported_crs_raw)
    if projection not in SUPPORTED_CRS:
        raise UnsupportedProjectionError(projection)

    zoom_levels = [
        int(identifier)
        for identifier in (
            _text_of_local(tm, "Identifier")
            for tm in _find_all_local(tile_matrix_set, "TileMatrix")
        )
        if identifier is not None and identifier.isdigit()
    ]
    if not zoom_levels:
        raise ValueError("TileMatrixSet declares no numbered TileMatrix levels")

    # Everything below is discovered purely for `tile_proxy.build_upstream_url`'s
    # WMTS KVP `GetTile` request — checked after the CRS/zoom gate above, which
    # is this module's real refusal reason, so a document with an unsupported
    # CRS is still rejected for *that* reason even if it also has no Style/Format.
    tile_matrix_set_name = _text_of_local(tile_matrix_set, "Identifier")
    if tile_matrix_set_name is None:
        raise ValueError("TileMatrixSet declares no Identifier")

    first_layer = layers[0]
    first_layer_name = layer_names[0] if layer_names else "?"
    format_text = _text_of_local(first_layer, "Format")
    if format_text is None:
        raise ValueError(f"layer {first_layer_name!r} declares no Format")
    style_el = _first_local_child(first_layer, "Style")
    style_id = _text_of_local(style_el, "Identifier") if style_el is not None else None
    if style_id is None:
        raise ValueError(f"layer {first_layer_name!r} declares no Style")

    return DiscoveredCapabilities(
        layers=layer_names,
        projection=projection,
        zoom_min=min(zoom_levels),
        zoom_max=max(zoom_levels),
        tile_matrix_set=tile_matrix_set_name,
        format=format_text,
        style=style_id,
    )


async def _http_get(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.content


async def register_tier4_provider(
    endpoint: str, *, http_get: Callable[[str], Awaitable[bytes]] = _http_get
) -> DiscoveredCapabilities:
    url = f"{endpoint}?SERVICE=WMTS&REQUEST=GetCapabilities"
    xml_bytes = await http_get(url)
    return parse_wmts_capabilities(xml_bytes)
