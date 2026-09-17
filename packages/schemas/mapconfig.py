"""The basemap provider registry — `docs/00_ARCHITECTURE.md` §1.2 ("The
provider registry"), ADR-014, ADR-015, ADR-016, `docs/07_BUILD_PLAN.md`
Phase 5. `osprey.yaml`'s `map:` section is data, not code: MapLibre
consumes any style plus vector or raster sources, so adding a provider is a
config change, never a code change (`00_ARCHITECTURE.md` §1.2's own line).

Pydantic is the source of truth here exactly as it is for `schemas.ingest`'s
`Recipe` — no separate JSON Schema file, and `services/api/mapconfig_loader.py`
mirrors `services/ingest/recipe_loader.py`'s `yaml.safe_load` +
`model_validate` shape precisely.

**Licence is always the structured form.** The architecture doc's own
worked examples are inconsistent — `osm-local` writes `licence: ODbL` (a
bare string) while `wmts-corporate` writes a structured
`{id, redistributable, client_scope}` object, and `os-ngd` writes a bare
string plus a separate top-level `licence_note`. ADR-016 is explicit that
`client_scope` is enforced, not documented, on *every* provider, and a
required field cannot be enforced against a shape that is sometimes a bare
string — so this module requires the structured `ProviderLicence` object
everywhere, folding `licence_note` into `ProviderLicence.note`. Recorded
here, not silently normalised, because it is a real inconsistency in the
input examples, not a typo in one of them.

TypeScript types are generated from these (`generate_ts.py`); a drift
between the two fails the build (`scripts/schemas_check.py`). Only the
fields the Glass's layer control actually needs travel to the frontend —
`services/api/mapconfig_loader.py`'s `public_view()` is what strips a tier 3
`credential` reference before the Conduit serves this to the browser.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MapSourceKind(StrEnum):
    """`00_ARCHITECTURE.md` §1.2: "Four source kinds cover the field.\""""

    VECTOR = "vector"
    RASTER = "raster"
    IMAGE = "image"
    DEM = "dem"


class OgcServiceKind(StrEnum):
    """Tier 4 (ADR-016): the four generic OGC service types. `None` on a
    provider means it is tiers 1-3 (a direct `source`), not tier 4."""

    WMTS = "wmts"
    WMS = "wms"
    WFS = "wfs"
    OGC_FEATURES = "ogc-features"


class ClientScope(StrEnum):
    """`00_ARCHITECTURE.md` §1.2: "`client_scope` is a required field on
    every provider" — the three values named there exactly."""

    OPEN = "open"
    PER_DEPLOYMENT = "per-deployment"
    PER_SEAT = "per-seat"


class ProviderLicence(BaseModel):
    id: str
    redistributable: bool
    client_scope: ClientScope
    note: str | None = None


class PrefetchCache(BaseModel):
    """Tier 3 only (`05_DEPLOYMENT.md` §2.2's "Prefetch area of
    operations") — absent for tiers 1/2/4, which either need no cache
    (local files) or aren't proxied through it the same way."""

    ttl_days: int = Field(gt=0)
    prefetch_areas: list[str] = Field(default_factory=list)


#: `credential` is a reference, never a value (`00_ARCHITECTURE.md` §1.2:
#: "a reference, never a value") — an environment variable *name*, so a
#: provider entry committed to `osprey.yaml` in version control can never
#: itself be a leaked secret.
_ENV_REFERENCE = re.compile(r"^env:[A-Za-z_][A-Za-z0-9_]*$")


class MapProvider(BaseModel):
    id: str
    label: str
    kind: MapSourceKind
    licence: ProviderLicence

    #: Tiers 1-3: a direct source URI (`file://...pmtiles`, `os-datahub://...`).
    #: Mutually exclusive with `service`/`endpoint` (tier 4) and `profile`
    #: (a `providers/*.yaml` reference) — exactly one of the three names
    #: how this provider resolves to tiles.
    source: str | None = None

    #: Tier 4 (ADR-016): capabilities are parsed at registration, not typed
    #: in by hand — `endpoint`/`layer` are what registration discovers.
    #: `endpoint` is always a bare service base URL (never a `{z}`/`{x}`/
    #: `{y}`-templated tile URL — `services/api/tile_proxy.py`'s
    #: `build_upstream_url` builds a real WMTS KVP `GetTile` request from
    #: it for `service: wmts`, Phase 5's known-gaps closure fixing the
    #: conflict this field's own history used to record here).
    service: OgcServiceKind | None = None
    endpoint: str | None = None
    layer: str | None = None

    #: WMTS KVP `GetTile` parameters, discovered by `register_tier4_provider`
    #: alongside `layer` and hand-copied into `osprey.yaml` the same way —
    #: only meaningful for `service: wmts`, but not enforced as required
    #: even then, since a provider entry is written by hand before this
    #: module ever validates it against a live capabilities document.
    tile_matrix_set: str | None = None
    format: str | None = None
    #: The WMTS `STYLE` KVP parameter — deliberately not named `style`,
    #: which already means the MapLibre style reference below; conflating
    #: the two would be a silent, confusing collision between an OGC wire
    #: parameter and a client rendering concern.
    wmts_style: str | None = None

    #: Discovered by the same registration call, alongside the above —
    #: `PrefetchCache`'s scheduled pre-warm job (`services/api/prefetch.py`)
    #: needs a zoom range and nothing else in this schema states one.
    zoom_min: int | None = None
    zoom_max: int | None = None

    #: A `providers/<profile>.yaml` reference (`00_ARCHITECTURE.md` §1.2's
    #: "Provider profiles") rather than an inline definition.
    profile: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)

    credential: str | None = None
    proxy: Literal["required", "recommended", "none"] = "none"
    cache: PrefetchCache | None = None

    #: `bundled:osprey-dark` / `bundled:osprey-light`, or a profile's own
    #: style reference. `None` only for `kind: image` (a site aerial photo
    #: has no basemap style of its own) and `kind: dem`.
    style: str | None = None
    attribution: str

    @model_validator(mode="after")
    def _exactly_one_resolution_path(self) -> MapProvider:
        paths = [
            self.source is not None,
            self.service is not None or self.endpoint is not None,
            self.profile is not None,
        ]
        if sum(paths) != 1:
            raise ValueError(
                f"provider {self.id!r} must set exactly one of source/"
                "service+endpoint/profile, not zero or several"
            )
        if self.service is not None and self.endpoint is None:
            raise ValueError(f"provider {self.id!r} declares service but not endpoint")
        return self

    @model_validator(mode="after")
    def _credential_is_a_reference_not_a_value(self) -> MapProvider:
        if self.credential is not None and not _ENV_REFERENCE.match(self.credential):
            raise ValueError(
                f"provider {self.id!r}'s credential must be an 'env:VAR_NAME' reference, "
                "never a literal value"
            )
        return self


class MapConfig(BaseModel):
    """`osprey.yaml`'s `map:` section."""

    default: str
    providers: list[MapProvider] = Field(min_length=1)

    @model_validator(mode="after")
    def _default_and_ids_are_consistent(self) -> MapConfig:
        ids = [p.id for p in self.providers]
        if len(set(ids)) != len(ids):
            raise ValueError("provider ids must be unique")
        if self.default not in ids:
            raise ValueError(f"default provider {self.default!r} is not a declared provider")
        return self


class PublicMapProvider(BaseModel):
    """What the Glass is allowed to see about one provider
    (`services/api/mapconfig_loader.py`'s `public_view()`) — everything
    needed to add a MapLibre layer and render attribution/licence notes,
    nothing that discloses internal wiring (a `credential` reference, a
    proxied tier 3/4 `endpoint`, `profile`/`variables`)."""

    id: str
    label: str
    kind: MapSourceKind
    style: str | None
    attribution: str
    licence_id: str
    licence_note: str | None
    #: `00_ARCHITECTURE.md` §1.2: "the map UI should show a hosted-provider
    #: indicator whenever a tier 3 layer is live" — `client_scope != "open"`
    #: is that signal (a hosted/entitled data source, tier 3 or a proxied
    #: non-open tier 4 profile), read straight off the licence rather than
    #: needing a second `proxy` field exposed here too.
    client_scope: ClientScope
    #: Only for a provider the browser fetches directly (tiers 1-2's local
    #: `source`). `None` for anything reached through the Conduit's tile
    #: proxy (a proxied tier-3/4 `endpoint`) or an unresolved `profile`
    #: reference — those get a proxy-relative URL once the tile proxy
    #: itself is built (`07_BUILD_PLAN.md` Phase 5's tier 2-4 checkpoint).
    source: str | None


class PublicMapConfig(BaseModel):
    """`GET /v1/map/providers`'s real response shape — a bare
    `list[PublicMapProvider]` has nowhere to carry which one is the
    default, and the Glass's layer control (`02_GLASS_FRONTEND.md` §3.5)
    needs that to pick an initial basemap without guessing (the first
    list entry is not necessarily `MapConfig.default`)."""

    default: str
    providers: list[PublicMapProvider]


ALL_MODELS: tuple[type[BaseModel], ...] = (
    ProviderLicence,
    PrefetchCache,
    MapProvider,
    MapConfig,
    PublicMapProvider,
    PublicMapConfig,
)
