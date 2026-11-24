// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PipelineId = string;
/**
 * @maxItems 500
 */
export type RunsAfter = string[];

/**
 * One pipeline and the pipelines it runs after.
 */
export interface RunOrderEntry {
  pipeline_id: PipelineId;
  runs_after?: RunsAfter;
}
