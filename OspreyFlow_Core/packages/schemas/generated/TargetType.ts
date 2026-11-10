// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "node" | "link";
export type Name = string;
export type Properties = string[];
export type Required = string[];

/**
 * A type of the target's live model, with what a drawn property may be mapped onto: its
 * properties and identifiers, and those it requires.
 */
export interface TargetType {
  kind: Kind;
  name: Name;
  properties: Properties;
  required?: Required;
}
