// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Day = string;
export type PipelineId = string;
export type PipelineLabel = string;
export type DatasetId = string | null;
export type Unit = string;
export type Trigger = "manual" | "schedule" | "watch" | "release" | "source_refresh" | "external";
export type Runs = number;
export type Succeeded = number;
export type Refused = number;
export type Failed = number;
export type WallMs = number;
export type RowsRead = number | null;
export type RowsStaged = number | null;
export type GraphWrites = number | null;
export type Withheld = boolean;

/**
 * One day of one pipeline's runs by one trigger (decision 3).
 */
export interface RollupRow {
  day: Day;
  pipeline_id: PipelineId;
  pipeline_label: PipelineLabel;
  dataset_id?: DatasetId;
  unit: Unit;
  trigger: Trigger;
  runs: Runs;
  succeeded: Succeeded;
  refused: Refused;
  failed: Failed;
  wall_ms: WallMs;
  rows_read?: RowsRead;
  rows_staged?: RowsStaged;
  graph_writes?: GraphWrites;
  withheld?: Withheld;
}
