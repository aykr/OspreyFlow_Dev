// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type PipelineId = string;
export type Version = number | "latest";
export type ExternalRunId = string;

/**
 * `POST /v1/runs` (decision 9): start a run of one pipeline at a deployed version, or the
 * latest deployed, keyed by the orchestrator's own run id (decision 12).
 */
export interface ExternalRunInput {
  dataset_id: DatasetId;
  pipeline_id: PipelineId;
  version?: Version;
  external_run_id: ExternalRunId;
}
