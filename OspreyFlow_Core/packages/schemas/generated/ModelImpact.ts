// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type LiveVersion = number | null;
export type DraftVersion = number;
export type PacksAdded = ("fibo" | "niem" | "stix")[];
export type PacksRemoved = ("fibo" | "niem" | "stix")[];
export type PacksRepinned = ("fibo" | "niem" | "stix")[];
export type ExtensionsAdded = string[];
export type ExtensionsRetired = string[];
export type ExtensionsRestored = string[];
export type ChangedTypes = string[];
export type RecipeId = string;
export type Label = string;
export type Writes = string[];
export type Pipelines = ImpactedPipeline[];
export type InvestigationId = string;
export type Name = string | null;
export type Cases = ImpactedCase[];
export type Composites = string[];

/**
 * `GET /v1/datasets/{dataset_id}/model/impact` (R12, ADR-140 decision 5): what making the
 * draft live would change, read before anything does. Loaded data is never rewritten.
 */
export interface ModelImpact {
  dataset_id: DatasetId;
  live_version: LiveVersion;
  draft_version: DraftVersion;
  packs_added?: PacksAdded;
  packs_removed?: PacksRemoved;
  packs_repinned?: PacksRepinned;
  extensions_added?: ExtensionsAdded;
  extensions_retired?: ExtensionsRetired;
  extensions_restored?: ExtensionsRestored;
  changed_types?: ChangedTypes;
  pipelines?: Pipelines;
  cases?: Cases;
  composites?: Composites;
  [k: string]: unknown;
}
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
/**
 * A case reading the dataset (directly or through a composite) that the reader may open.
 * Cases they may not open are not listed and not counted (rule 7).
 */
export interface ImpactedCase {
  investigation_id: InvestigationId;
  name?: Name;
  [k: string]: unknown;
}
