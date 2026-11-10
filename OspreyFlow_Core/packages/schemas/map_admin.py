"""*Admin › Maps* (`06_DECISIONS.md` ADR-147): the deployment's basemap providers, each with its
state, added and edited; a provider's key under ADR-135 Amendment 2's rule (managed in Admin,
write-only, never returned, logged or echoed, every change audited, behind `manage_geospatial`);
the local basemap's state and its glyph fonts; prefetch areas run on a schedule.

A key arrives once, as `SecretStr`, and is never returned: a provider's record says only whether
a key is held, and where (`set` in the Conduit's map key file, `env` named by `osprey.yaml`'s
`credential: env:VAR`, or `none`). No response model here has a field that could hold one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from schemas.mapconfig import MapProvider

#: `00_ARCHITECTURE.md` §1.2's four tiers: 1 local files, 2 a site image or other local layer,
#: 3 a hosted provider through the tile proxy, 4 a generic OGC service.
MapTier = Literal[1, 2, 3, 4]
MapKeyState = Literal["set", "env", "none"]
MapAdminAction = Literal[
    "provider_added",
    "provider_edited",
    "provider_removed",
    "default_changed",
    "key_set",
    "key_removed",
    "areas_changed",
    "schedule_changed",
    "prefetch_run",
    "basemap_built",
    "basemap_verified",
]

#: The most tiles one area may ask for, every zoom counted (ADR-147 decision 5). Larger is refused
#: in words with the count, never cut to fit (rule 2).
MAX_AREA_TILES = 5000


class AdminMapProvider(BaseModel):
    """One provider as *Admin › Maps* shows it."""

    provider: MapProvider
    tier: MapTier
    #: Where its key is, never the key: `set` (the map key file), `env` (osprey.yaml's reference)
    #: or `none`.
    key_state: MapKeyState
    #: Whether its tiles need a key at all (a `credential`, a `credential_param` or a
    #: `{credential}` in its address).
    needs_key: bool
    key_set_at: datetime | None = None
    key_set_by: str | None = None
    #: Plain words for its state: ready, a key missing, a local file not built, and so on.
    state: str
    ready: bool


class LocalBasemap(BaseModel):
    """A tier-1 provider's local file, as the Conduit sees it."""

    provider_id: str
    #: The file's name in the tiles folder, never a host path.
    file: str
    built: bool
    size_bytes: int | None = None
    built_at: datetime | None = None


class BasemapState(BaseModel):
    basemaps: list[LocalBasemap]
    #: The place-name glyphs the bundled style asks for (`scripts/fetch_basemap_glyphs.py`).
    glyphs_installed: bool
    glyph_fonts: list[str]
    #: Whether the map builder can run here: Java and the planetiler jar in the tiles folder.
    builder_ready: bool
    builder_state: str
    regions: list[str]


class PrefetchArea(BaseModel):
    """A named box whose tiles are fetched ahead of use, for one proxied, cached provider
    (ADR-147 decision 5). Degrees, WGS84; zooms inclusive."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    provider_id: str = Field(min_length=1)
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-85.0511, le=85.0511)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-85.0511, le=85.0511)
    zoom_min: int = Field(ge=0, le=22)
    zoom_max: int = Field(ge=0, le=22)

    @model_validator(mode="after")
    def _a_real_box(self) -> PrefetchArea:
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("an area's west must be less than its east, and its south its north")
        if self.zoom_min > self.zoom_max:
            raise ValueError("an area's lowest zoom must not be above its highest")
        return self


class PrefetchSchedule(BaseModel):
    """Every area is fetched again this often; `None` means by hand only."""

    model_config = ConfigDict(extra="forbid")

    #: Every 6 hours, every day or every week (ADR-147 decision 5); `None` is by hand only.
    every_hours: Literal[6, 24, 168] | None = None


class PrefetchRun(BaseModel):
    """One area's last run: counts only."""

    area: str
    provider_id: str
    at: datetime
    tiles_fetched: int
    tiles_already_cached: int
    #: Fixed words when it did not finish; never the provider's words or address.
    failed: str | None = None


class PrefetchAreaView(BaseModel):
    area: PrefetchArea
    tiles: int
    last_run: PrefetchRun | None = None


class MapsAdminView(BaseModel):
    """`GET /v1/admin/maps`."""

    default: str
    providers: list[AdminMapProvider]
    #: True once *Admin › Maps* has changed anything: the maps file then replaces `osprey.yaml`'s
    #: `map:` whole.
    changed_in_admin: bool
    basemap: BasemapState
    areas: list[PrefetchAreaView]
    schedule: PrefetchSchedule
    next_run_at: datetime | None = None


class MapProviderInput(BaseModel):
    """A provider added or edited; validated as `MapProvider` is. An `env:` credential reference is
    the installer's way and stays possible; a key typed in Admin goes through `MapKeyInput`."""

    model_config = ConfigDict(extra="forbid")

    provider: MapProvider


class MapDefaultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str = Field(min_length=1)


class MapKeyInput(BaseModel):
    """`PUT /v1/admin/maps/providers/{id}/key`. Write-only: never echoed, logged or returned."""

    model_config = ConfigDict(extra="forbid")

    key: SecretStr = Field(min_length=1, max_length=4096)


class PrefetchAreasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    areas: list[PrefetchArea] = Field(max_length=50)


class PrefetchScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: PrefetchSchedule


class BuildBasemapInput(BaseModel):
    """`POST /v1/admin/geospatial/build-basemap`: a named region only. The tiles folder and the
    planetiler jar are the deployment's own, never a path typed in the Glass."""

    model_config = ConfigDict(extra="forbid")

    region: str = Field(min_length=1)
    #: ADR-147 Amendment 2 (the owner's ruling 8): the unit the gazetteer's places and dataset are
    #: held by. One that holds a case or a dataset here, or the administrator's own (the default).
    unit: str | None = Field(default=None, min_length=1, max_length=64)


class MapAdminEntry(BaseModel):
    """One row of the maps' history. Never a key, a fragment, a hash or a length."""

    at: datetime
    by: str
    action: MapAdminAction
    provider: str | None = None
    #: Each changed field's old and new value (none of them secret: a key is never one).
    changes: dict[str, dict[str, object]] = Field(default_factory=dict)
    outcome: str


class MapAdminHistory(BaseModel):
    entries: list[MapAdminEntry]


ALL_MODELS: tuple[type[BaseModel], ...] = (
    AdminMapProvider,
    LocalBasemap,
    BasemapState,
    PrefetchArea,
    PrefetchSchedule,
    PrefetchRun,
    PrefetchAreaView,
    MapsAdminView,
    MapProviderInput,
    MapDefaultInput,
    MapKeyInput,
    PrefetchAreasInput,
    PrefetchScheduleInput,
    BuildBasemapInput,
    MapAdminEntry,
    MapAdminHistory,
)
