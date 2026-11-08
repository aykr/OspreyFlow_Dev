// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecipeId = string;
export type Label = string;
export type CaseId = string | null;
export type Cron = string | null;
export type Watch = string | null;
export type Timezone = string;
export type Schedule = string;
export type Owner = string | null;
export type NextRun = string | null;
export type Paused = boolean;
export type PausedReason = string | null;
export type Flagged = boolean;
export type RunId = string;
export type Trigger = "manual" | "schedule" | "watch" | "release" | "source_refresh";
export type Slot = string | null;
export type StartedAt = string;
export type FinishedAt = string | null;
export type Outcome = "running" | "succeeded" | "failed" | "refused" | "blocked" | "skipped" | "missed";
export type RunAs = string;
export type Withheld = boolean;
export type RowsRead = number | null;
export type NodesCreated = number | null;
export type NodesReferenced = number | null;
export type EdgesCreated = number | null;
export type RowsRejected = number | null;
export type RowsHeld = number | null;
export type LoadId = string | null;
export type Failure = string | null;
export type File = string | null;
export type WallMs = number;
export type RowsRead1 = number;
export type RowsStaged = number | null;
export type ParquetBytes = number | null;
export type ObjectStoreBytes = number | null;
export type GraphWrites = number;

/**
 * A scheduled recipe in the Admin area's *Schedules and runs* (ADR-110 decision 8).
 */
export interface AdminSchedule {
  recipe_id: RecipeId;
  label: Label;
  case_id?: CaseId;
  cron?: Cron;
  watch?: Watch;
  timezone: Timezone;
  schedule: Schedule;
  owner?: Owner;
  next_run?: NextRun;
  paused?: Paused;
  paused_reason?: PausedReason;
  flagged?: Flagged;
  last_run?: ScheduleRunView | null;
  [k: string]: unknown;
}
/**
 * One row of the run ledger as the Admin area shows it (ADR-110 decisions 6 and 8). Where the
 * reader may not view the source, `withheld` is set and the counts and the failure's words are
 * left out: a count of what a load wrote is a read (rule 3).
 */
export interface ScheduleRunView {
  run_id: RunId;
  trigger: Trigger;
  slot?: Slot;
  started_at: StartedAt;
  finished_at?: FinishedAt;
  outcome: Outcome;
  run_as: RunAs;
  withheld?: Withheld;
  rows_read?: RowsRead;
  nodes_created?: NodesCreated;
  nodes_referenced?: NodesReferenced;
  edges_created?: EdgesCreated;
  rows_rejected?: RowsRejected;
  rows_held?: RowsHeld;
  load_id?: LoadId;
  failure?: Failure;
  file?: File;
  metering?: RunMetering | null;
  [k: string]: unknown;
}
/**
 * What a run cost (ADR-110 Amendment 6 point 9, ADR-141 decision 2;
 * `services/ingest/metering.py` has how each is counted). `None` is *not measured*, never 0:
 * rows staged and bytes written to Parquet are a staged run's (ADR-140 Amendment 12), `None` for
 * any other. Counts of the run's own rows and writes: a route withholds them as it withholds
 * every count (rule 3).
 */
export interface RunMetering {
  wall_ms: WallMs;
  rows_read: RowsRead1;
  rows_staged?: RowsStaged;
  parquet_bytes?: ParquetBytes;
  object_store_bytes?: ObjectStoreBytes;
  graph_writes: GraphWrites;
  [k: string]: unknown;
}
