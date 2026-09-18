// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Id = string;
export type Label = string;
/**
 * `00_ARCHITECTURE.md` §1.2: "Four source kinds cover the field."
 */
export type MapSourceKind = "vector" | "raster" | "image" | "dem";
export type Style = string | null;
export type Attribution = string;
export type LicenceId = string;
export type LicenceNote = string | null;
/**
 * `00_ARCHITECTURE.md` §1.2: "`client_scope` is a required field on
 * every provider" — the three values named there exactly.
 */
export type ClientScope = "open" | "per-deployment" | "per-seat";
export type Source = string | null;

/**
 * What the Glass is allowed to see about one provider
 * (`services/api/mapconfig_loader.py`'s `public_view()`) — everything
 * needed to add a MapLibre layer and render attribution/licence notes,
 * nothing that discloses internal wiring (a `credential` reference, a
 * proxied tier 3/4 `endpoint`, `profile`/`variables`).
 */
export interface PublicMapProvider {
  id: Id;
  label: Label;
  kind: MapSourceKind;
  style: Style;
  attribution: Attribution;
  licence_id: LicenceId;
  licence_note: LicenceNote;
  client_scope: ClientScope;
  source: Source;
  [k: string]: unknown;
}
