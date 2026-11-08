// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type Version = number;
export type State = "draft" | "live" | "previous";
export type Name = string;
export type Kind = "entity_type" | "link_type" | "property";
export type OnType = string | null;
export type AddedIn = number;
export type RetiredIn = number | null;
export type Extensions = ModelExtension[];
export type ReferenceLists = string[];
export type CreatedAt = string;
export type PrincipalId = string;
export type MadeLiveAt = string | null;
export type RevertedFrom = number | null;
export type RecipeId = string;
export type Label = string;
export type Writes = string[];
export type Flagged = ImpactedPipeline[];

/**
 * `POST /v1/datasets/{dataset_id}/model/make-live`'s answer: the version now live, the one it
 * replaced, and each pipeline marked as needing attention, its schedule paused with the reason.
 */
export interface MadeLive {
  live: TargetModel;
  previous?: TargetModel | null;
  flagged?: Flagged;
  [k: string]: unknown;
}
/**
 * One version of a dataset's domain model (R3, R12).
 */
export interface TargetModel {
  dataset_id: DatasetId;
  version: Version;
  state: State;
  packs?: Packs;
  extensions?: Extensions;
  reference_lists?: ReferenceLists;
  created_at: CreatedAt;
  created_by: PrincipalId;
  made_live_at?: MadeLiveAt;
  made_live_by?: PrincipalId | null;
  reverted_from?: RevertedFrom;
}
export interface Packs {
  [k: string]: number;
}
/**
 * A type or property the dataset's own model adds beyond the core and its packs (ADR-140
 * decision 4; today's analyst-proposed type, ADR-090). Retired, never deleted: a rename is "add
 * the new, retire the old".
 */
export interface ModelExtension {
  name: Name;
  kind: Kind;
  on_type?: OnType;
  added_in: AddedIn;
  retired_in?: RetiredIn;
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
