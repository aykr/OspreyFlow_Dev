// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type Default = string;
export type Options = string[];

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
