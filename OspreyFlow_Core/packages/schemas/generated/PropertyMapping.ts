// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DrawnProperty = string;
export type TargetProperty = string | null;

/**
 * One drawn property and the property (or identifier) of the chosen type it goes in as, or
 * `None`: not carried (it stays on the drawing, read-only, and is said).
 */
export interface PropertyMapping {
  drawn_property: DrawnProperty;
  target_property: TargetProperty;
}
