// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ExpectedVersion = number;
export type PipelineId = string;
/**
 * @maxItems 500
 */
export type RunsAfter = string[];
/**
 * @maxItems 500
 */
export type Entries = RunOrderEntry[];

/**
 * A save: the links as the person now has them, and the number of the stored order they read
 * (0 when none was stored). The number is required and is an integer, never a string or a flag:
 * a client that sends none cannot skip the check.
 */
export interface RunOrderSave {
  expected_version: ExpectedVersion;
  entries: Entries;
}
/**
 * One pipeline and the pipelines it runs after.
 */
export interface RunOrderEntry {
  pipeline_id: PipelineId;
  runs_after?: RunsAfter;
}
