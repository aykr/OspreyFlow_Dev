// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Default = string;
/**
 * The provider's own name, as map.default names it
 */
export type Id = string;
/**
 * What the Glass's map menu calls it
 */
export type Label = string;
/**
 * `00_ARCHITECTURE.md` §1.2: "Four source kinds cover the field."
 */
export type MapSourceKind = "vector" | "raster" | "image" | "dem";
/**
 * The licence's identifier, e.g. ODbL-1.0 or OGL-UK-3.0
 */
export type Id1 = string;
/**
 * Whether the tiles may be passed on to others
 */
export type Redistributable = boolean;
/**
 * Who the licence covers: anyone, this deployment, or each seat
 */
export type ClientScope = "open" | "per-deployment" | "per-seat";
/**
 * Anything the licence asks to be said
 */
export type Note = string | null;
/**
 * Where the tiles are: a file (file://…pmtiles) or a provider's address; one of source, service and endpoint, or profile
 */
export type Source = string | null;
/**
 * Tier 4 (ADR-016): the four generic OGC service types. `None` on a
 * provider means it is tiers 1-3 (a direct `source`), not tier 4.
 */
export type OgcServiceKind = "wmts" | "wms" | "wfs" | "ogc-features";
/**
 * An OGC service's base address (with service), never a tile URL
 */
export type Endpoint = string | null;
/**
 * The service's layer to show
 */
export type Layer = string | null;
/**
 * WMTS: the tile matrix set
 */
export type TileMatrixSet = string | null;
/**
 * WMTS: the tile image format
 */
export type Format = string | null;
/**
 * WMTS: the service's STYLE
 */
export type WmtsStyle = string | null;
/**
 * The lowest zoom the provider serves
 */
export type ZoomMin = number | null;
/**
 * The highest zoom the provider serves
 */
export type ZoomMax = number | null;
/**
 * A ready-made provider (providers/<profile>.yaml) to use
 */
export type Profile = string | null;
/**
 * The provider's key, as env:VARIABLE — a name, never the key itself
 */
export type Credential = string | null;
/**
 * WMTS: the query parameter the provider's key goes in
 */
export type CredentialParam = string | null;
/**
 * Whether tiles are fetched through the Conduit (which caches them and keeps the key on the server) rather than by the browser
 */
export type Proxy = "required" | "recommended" | "none";
/**
 * How long a fetched tile is kept, in days
 */
export type TtlDays = number;
/**
 * Areas whose tiles are fetched ahead of use
 */
export type PrefetchAreas = string[];
/**
 * The map style: bundled:osprey-dark, bundled:osprey-light, or the profile's own
 */
export type Style = string | null;
/**
 * The credit shown on the map, as the licence asks
 */
export type Attribution = string;
export type Tier = 1 | 2 | 3 | 4;
export type KeyState = "set" | "env" | "none";
export type NeedsKey = boolean;
export type KeySetAt = string | null;
export type KeySetBy = string | null;
export type State = string;
export type Ready = boolean;
export type Providers = AdminMapProvider[];
export type ChangedInAdmin = boolean;
export type ProviderId = string;
export type File = string;
export type Built = boolean;
export type SizeBytes = number | null;
export type BuiltAt = string | null;
export type Basemaps = LocalBasemap[];
export type GlyphsInstalled = boolean;
export type GlyphFonts = string[];
export type BuilderReady = boolean;
export type BuilderState = string;
export type Regions = string[];
export type Name = string;
export type ProviderId1 = string;
export type West = number;
export type South = number;
export type East = number;
export type North = number;
export type ZoomMin1 = number;
export type ZoomMax1 = number;
export type Tiles = number;
export type Area = string;
export type ProviderId2 = string;
export type At = string;
export type TilesFetched = number;
export type TilesAlreadyCached = number;
export type Failed = string | null;
export type Areas = PrefetchAreaView[];
export type EveryHours = (6 | 24 | 168) | null;
export type NextRunAt = string | null;

/**
 * `GET /v1/admin/maps`.
 */
export interface MapsAdminView {
  default: Default;
  providers: Providers;
  changed_in_admin: ChangedInAdmin;
  basemap: BasemapState;
  areas: Areas;
  schedule: PrefetchSchedule;
  next_run_at?: NextRunAt;
  [k: string]: unknown;
}
/**
 * One provider as *Admin › Maps* shows it.
 */
export interface AdminMapProvider {
  provider: MapProvider;
  tier: Tier;
  key_state: KeyState;
  needs_key: NeedsKey;
  key_set_at?: KeySetAt;
  key_set_by?: KeySetBy;
  state: State;
  ready: Ready;
  [k: string]: unknown;
}
export interface MapProvider {
  id: Id;
  label: Label;
  kind: MapSourceKind;
  licence: ProviderLicence;
  source?: Source;
  service?: OgcServiceKind | null;
  endpoint?: Endpoint;
  layer?: Layer;
  tile_matrix_set?: TileMatrixSet;
  format?: Format;
  wmts_style?: WmtsStyle;
  zoom_min?: ZoomMin;
  zoom_max?: ZoomMax;
  profile?: Profile;
  variables?: Variables;
  credential?: Credential;
  credential_param?: CredentialParam;
  proxy?: Proxy;
  /**
   * Keep fetched tiles a while
   */
  cache?: PrefetchCache | null;
  style?: Style;
  attribution: Attribution;
  [k: string]: unknown;
}
/**
 * The terms the tiles come under
 */
export interface ProviderLicence {
  id: Id1;
  redistributable: Redistributable;
  client_scope: ClientScope;
  note?: Note;
  [k: string]: unknown;
}
/**
 * Values the profile's addresses are filled with
 */
export interface Variables {
  [k: string]: string;
}
/**
 * Tier 3 only (`05_DEPLOYMENT.md` §2.2's "Prefetch area of
 * operations") — absent for tiers 1/2/4, which either need no cache
 * (local files) or aren't proxied through it the same way.
 */
export interface PrefetchCache {
  ttl_days: TtlDays;
  prefetch_areas?: PrefetchAreas;
  [k: string]: unknown;
}
export interface BasemapState {
  basemaps: Basemaps;
  glyphs_installed: GlyphsInstalled;
  glyph_fonts: GlyphFonts;
  builder_ready: BuilderReady;
  builder_state: BuilderState;
  regions: Regions;
  [k: string]: unknown;
}
/**
 * A tier-1 provider's local file, as the Conduit sees it.
 */
export interface LocalBasemap {
  provider_id: ProviderId;
  file: File;
  built: Built;
  size_bytes?: SizeBytes;
  built_at?: BuiltAt;
  [k: string]: unknown;
}
export interface PrefetchAreaView {
  area: PrefetchArea;
  tiles: Tiles;
  last_run?: PrefetchRun | null;
  [k: string]: unknown;
}
/**
 * A named box whose tiles are fetched ahead of use, for one proxied, cached provider
 * (ADR-147 decision 5). Degrees, WGS84; zooms inclusive.
 */
export interface PrefetchArea {
  name: Name;
  provider_id: ProviderId1;
  west: West;
  south: South;
  east: East;
  north: North;
  zoom_min: ZoomMin1;
  zoom_max: ZoomMax1;
}
/**
 * One area's last run: counts only.
 */
export interface PrefetchRun {
  area: Area;
  provider_id: ProviderId2;
  at: At;
  tiles_fetched: TilesFetched;
  tiles_already_cached: TilesAlreadyCached;
  failed?: Failed;
  [k: string]: unknown;
}
/**
 * Every area is fetched again this often; `None` means by hand only.
 */
export interface PrefetchSchedule {
  every_hours?: EveryHours;
}
