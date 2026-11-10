// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RunId = string;
export type PipelineId = string;
export type Version = number;
export type ExternalRunId = string;
export type Outcome = "running" | "succeeded" | "failed" | "refused";
export type StartedAt = string;
export type FinishedAt = string | null;
export type Words = string | null;
export type AlreadyRecorded = boolean;
export type RowsRead = number | null;
export type RowsRejected = number | null;
export type RowsHeld = number | null;
export type GraphWrites = number | null;
export type Withheld = boolean;

/**
 * `GET /v1/runs/{run_id}`: a run's status, its report's counts and its held rows.
 */
export interface ExternalRunStatus {
  run_id: RunId;
  pipeline_id: PipelineId;
  version: Version;
  external_run_id: ExternalRunId;
  outcome: Outcome;
  started_at: StartedAt;
  finished_at?: FinishedAt;
  words?: Words;
  already_recorded?: AlreadyRecorded;
  rows_read?: RowsRead;
  rows_rejected?: RowsRejected;
  rows_held?: RowsHeld;
  graph_writes?: GraphWrites;
  withheld?: Withheld;
}
