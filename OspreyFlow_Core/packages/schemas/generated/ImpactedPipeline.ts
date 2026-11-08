// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecipeId = string;
export type Label = string;
export type Writes = string[];

/**
 * A deployed pipeline of the dataset that writes a type the draft changes or retires: *Make
 * live* marks it as needing attention and pauses its schedule, with the reason.
 */
export interface ImpactedPipeline {
  recipe_id: RecipeId;
  label: Label;
  writes: Writes;
  [k: string]: unknown;
}
