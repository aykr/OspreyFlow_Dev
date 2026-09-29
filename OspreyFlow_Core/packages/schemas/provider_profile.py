"""Provider profiles — `spec/00_ARCHITECTURE.md` §1.2's "Provider profiles"
subsection, ADR-016 (`spec/06_DECISIONS.md`). A profile is a validated YAML
file in `providers/`, not code: it declares the endpoint shape, style
mapping, attribution, licence terms and auth pattern for a provider beyond
the four shipped tiers. `schemas.mapconfig.MapProvider.profile` references
one by id rather than inlining it — this is the schema for the file that
reference points at.

Reuses `MapSourceKind`/`ProviderLicence` from `schemas.mapconfig` rather
than duplicating them: a profile's `licence` carries exactly the same shape
a tier 1-4 provider's does, and `kind` is the same four-value enum.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas.mapconfig import MapSourceKind, ProviderLicence


class ProfileServiceKind(StrEnum):
    """`00_ARCHITECTURE.md` §1.2's worked profile example: "xyz | wmts | wms
    | wfs | ogc-features | pmtiles | mvt | image" — a superset of
    `mapconfig.OgcServiceKind`, since a profile can also describe a raw
    XYZ/PMTiles/MVT/image endpoint a bare tier 1-4 `MapProvider` entry
    cannot (those go through `source`/`service`+`endpoint` directly)."""

    XYZ = "xyz"
    WMTS = "wmts"
    WMS = "wms"
    WFS = "wfs"
    OGC_FEATURES = "ogc-features"
    PMTILES = "pmtiles"
    MVT = "mvt"
    IMAGE = "image"


class ProfileAuthType(StrEnum):
    """`00_ARCHITECTURE.md` §1.2's worked example: "none | api_key_query |
    api_key_header | bearer | basic | oauth2", named exactly."""

    NONE = "none"
    API_KEY_QUERY = "api_key_query"
    API_KEY_HEADER = "api_key_header"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


class ProfileAuth(BaseModel):
    type: ProfileAuthType


class ProfileVariable(BaseModel):
    """One `variables.<name>` entry — the worked example's `service:
    {default: "World_Imagery", options: [World_Imagery, World_Topo_Map]}`
    shape, letting a profile offer a choice (e.g. which USGS National Map
    layer) without becoming several profiles."""

    default: str
    options: list[str] = Field(default_factory=list)


#: A bare `EPSG:<code>` reference — `00_ARCHITECTURE.md` §1.2.2's CRS table
#: names every projection this platform deals with this way (EPSG:3857,
#: EPSG:4326, EPSG:27700, EPSG:4269).
_EPSG_CODE = re.compile(r"^EPSG:\d+$")


class ProfileZoom(BaseModel):
    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def _max_is_at_least_min(self) -> ProfileZoom:
        if self.max < self.min:
            raise ValueError(f"zoom.max ({self.max}) must be >= zoom.min ({self.min})")
        return self


class ProviderProfile(BaseModel):
    """One `providers/<id>.yaml` file — `00_ARCHITECTURE.md` §1.2's worked
    `esri-arcgis-online.yaml` example, field for field."""

    id: str
    label: str
    vendor: str
    kind: MapSourceKind
    service: ProfileServiceKind
    #: A URL template (`{z}`/`{x}`/`{y}`/a `variables` key in braces) — not
    #: resolved or fetched here; registration/`verify_map` (Checkpoint 3c)
    #: is what actually calls it.
    endpoint: str
    variables: dict[str, ProfileVariable] = Field(default_factory=dict)
    auth: ProfileAuth
    projection: str
    zoom: ProfileZoom
    #: `None` only for a `kind: image`/`kind: dem` profile, same as
    #: `MapProvider.style`.
    style: str | None = None
    attribution: str
    licence: ProviderLicence
    proxy: Literal["required", "recommended", "none"] = "none"

    @model_validator(mode="after")
    def _projection_is_an_epsg_code(self) -> ProviderProfile:
        if not _EPSG_CODE.match(self.projection):
            raise ValueError(
                f"profile {self.id!r}'s projection must be an 'EPSG:<code>' reference, "
                f"got {self.projection!r}"
            )
        return self


ALL_MODELS: tuple[type[BaseModel], ...] = (
    ProfileAuth,
    ProfileVariable,
    ProfileZoom,
    ProviderProfile,
)
