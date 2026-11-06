// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecipeId = string;
export type Label = string;
export type Version = number;
export type Status = string;

/**
 * A pipeline that uses a source: what the source page lists under *Lineage*.
 */
export interface SourceLineage {
  recipe_id: RecipeId;
  label: Label;
  version: Version;
  status: Status;
  [k: string]: unknown;
}
