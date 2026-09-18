// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Vendor = string;
/**
 * `00_ARCHITECTURE.md` §1.2: "Four source kinds cover the field."
 */
export type MapSourceKind = "vector" | "raster" | "image" | "dem";
/**
 * `00_ARCHITECTURE.md` §1.2's worked profile example: "xyz | wmts | wms
 * | wfs | ogc-features | pmtiles | mvt | image" — a superset of
 * `mapconfig.OgcServiceKind`, since a profile can also describe a raw
 * XYZ/PMTiles/MVT/image endpoint a bare tier 1-4 `MapProvider` entry
 * cannot (those go through `source`/`service`+`endpoint` directly).
 */
export type ProfileServiceKind = "xyz" | "wmts" | "wms" | "wfs" | "ogc-features" | "pmtiles" | "mvt" | "image";
export type Endpoint = string;
export type Default = string;
export type Options = string[];
/**
 * `00_ARCHITECTURE.md` §1.2's worked example: "none | api_key_query |
 * api_key_header | bearer | basic | oauth2", named exactly.
 */
export type ProfileAuthType = "none" | "api_key_query" | "api_key_header" | "bearer" | "basic" | "oauth2";
export type Projection = string;
export type Min = number;
export type Max = number;
export type Style = string | null;
export type Attribution = string;
export type Id1 = string;
export type Redistributable = boolean;
/**
 * `00_ARCHITECTURE.md` §1.2: "`client_scope` is a required field on
 * every provider" — the three values named there exactly.
 */
export type ClientScope = "open" | "per-deployment" | "per-seat";
export type Note = string | null;
export type Proxy = "required" | "recommended" | "none";

/**
 * One `providers/<id>.yaml` file — `00_ARCHITECTURE.md` §1.2's worked
 * `esri-arcgis-online.yaml` example, field for field.
 */
export interface ProviderProfile {
  id: Id;
  label: Label;
  vendor: Vendor;
  kind: MapSourceKind;
  service: ProfileServiceKind;
  endpoint: Endpoint;
  variables?: Variables;
  auth: ProfileAuth;
  projection: Projection;
  zoom: ProfileZoom;
  style?: Style;
  attribution: Attribution;
  licence: ProviderLicence;
  proxy?: Proxy;
  [k: string]: unknown;
}
export interface Variables {
  [k: string]: ProfileVariable;
}
/**
 * One `variables.<name>` entry — the worked example's `service:
 * {default: "World_Imagery", options: [World_Imagery, World_Topo_Map]}`
 * shape, letting a profile offer a choice (e.g. which USGS National Map
 * layer) without becoming several profiles.
 */
export interface ProfileVariable {
  default: Default;
  options?: Options;
  [k: string]: unknown;
}
export interface ProfileAuth {
  type: ProfileAuthType;
  [k: string]: unknown;
}
export interface ProfileZoom {
  min: Min;
  max: Max;
  [k: string]: unknown;
}
export interface ProviderLicence {
  id: Id1;
  redistributable: Redistributable;
  client_scope: ClientScope;
  note?: Note;
  [k: string]: unknown;
}
