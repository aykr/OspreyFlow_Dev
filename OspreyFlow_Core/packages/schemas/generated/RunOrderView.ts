// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type Version = number;
export type SavedBy = string | null;
export type SavedAt = string | null;
export type PipelineId = string;
/**
 * @maxItems 500
 */
export type RunsAfter = string[];
export type Entries = RunOrderEntry[];

/**
 * The stored order as the reader may see it: only the links among the pipelines they may
 * see, and no entry for a pipeline with none (so an entry never says that a pipeline runs
 * after something it may not name). `version` is 0, with no `saved_by` and no `saved_at`, when
 * no order has been saved.
 */
export interface RunOrderView {
  dataset_id: DatasetId;
  version: Version;
  saved_by?: SavedBy;
  saved_at?: SavedAt;
  entries: Entries;
}
/**
 * One pipeline and the pipelines it runs after.
 */
export interface RunOrderEntry {
  pipeline_id: PipelineId;
  runs_after?: RunsAfter;
}
