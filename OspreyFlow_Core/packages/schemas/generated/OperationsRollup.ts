// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Days = number;
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
export type Rows = RollupRow[];
export type Skipped = number;
export type Missed = number;
export type Reason = string;
export type Count = number;
export type Refused1 = RefusalCount[];
export type PipelineId1 = string;
export type PipelineLabel1 = string;
export type Reason1 = string | null;
export type Paused = PausedPipeline[];
export type RunningNow = number;
export type RunId = string;
export type PipelineLabel2 = string;
export type ServiceIdentity = string;
export type RanAsName = string;
export type StartedAt = string;
export type Outcome = string;
export type WallMs1 = number | null;
export type Withheld1 = boolean;
export type External = ExternalTrigger[];
export type Scope = "dataset" | "unit";
export type Key = string;
export type RunsPerDay = number | null;
export type AlertAtShare = number;
export type Quotas = RunQuota[];
export type Scope1 = "dataset" | "unit";
export type Key1 = string;
export type Day1 = string;
export type Words = string;
export type Alerts = QuotaAlertView[];
export type Units = string[];

/**
 * `GET /v1/admin/operations/runs`: the window's days, newest first, the reader's unit's alone
 * unless the reader administers the system (the redesign's phase 10 step 7).
 */
export interface OperationsRollup {
  days: Days;
  rows?: Rows;
  scheduler: SchedulerHealth;
  external?: External;
  quotas?: Quotas;
  alerts?: Alerts;
  units?: Units;
}
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
/**
 * Decision 4: what the executor already records, counted over the window.
 */
export interface SchedulerHealth {
  skipped: Skipped;
  missed: Missed;
  refused?: Refused1;
  paused?: Paused;
  running_now: RunningNow;
}
export interface RefusalCount {
  reason: Reason;
  count: Count;
}
export interface PausedPipeline {
  pipeline_id: PipelineId1;
  pipeline_label: PipelineLabel1;
  reason?: Reason1;
}
/**
 * Decision 14: an external trigger, with its service identity, who it ran as, and its cost.
 */
export interface ExternalTrigger {
  run_id: RunId;
  pipeline_label: PipelineLabel2;
  service_identity: ServiceIdentity;
  ran_as_name: RanAsName;
  started_at: StartedAt;
  outcome: Outcome;
  wall_ms?: WallMs1;
  withheld?: Withheld1;
}
/**
 * A dataset's or a unit's quota (decision 6). `None` is no limit. A run past a quota is refused
 * in words at the run path, whatever triggered it; `alert_at_share` of a quota raises the budget
 * alert to the administrators first.
 */
export interface RunQuota {
  scope: Scope;
  key: Key;
  runs_per_day?: RunsPerDay;
  alert_at_share?: AlertAtShare;
}
/**
 * A budget alert (decision 6): a quota's day reached its alert share.
 */
export interface QuotaAlertView {
  scope: Scope1;
  key: Key1;
  day: Day1;
  words: Words;
}
