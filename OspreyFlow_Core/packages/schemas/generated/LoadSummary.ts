// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LoadId = string | null;
export type RecipeId = string | null;
export type RecipeVersion = number | null;
export type Nodes = number;
export type Links = number;
export type Latest = string;

/**
 * One load into the case's datasets (ADR-100 decision 7), as far as the reader can see it:
 * only what it wrote that they can see is counted, and `latest` is the newest of those.
 */
export interface LoadSummary {
  load_id: LoadId;
  recipe_id?: RecipeId;
  recipe_version?: RecipeVersion;
  nodes: Nodes;
  links: Links;
  latest: Latest;
  [k: string]: unknown;
}
