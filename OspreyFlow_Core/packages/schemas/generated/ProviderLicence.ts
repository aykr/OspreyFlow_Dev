// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * The licence's identifier, e.g. ODbL-1.0 or OGL-UK-3.0
 */
export type Id = string;
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

export interface ProviderLicence {
  id: Id;
  redistributable: Redistributable;
  client_scope: ClientScope;
  note?: Note;
  [k: string]: unknown;
}
