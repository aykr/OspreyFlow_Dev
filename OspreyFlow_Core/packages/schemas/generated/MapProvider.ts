// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
