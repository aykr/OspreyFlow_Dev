// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Skipped = number;
export type Missed = number;
export type Reason = string;
export type Count = number;
export type Refused = RefusalCount[];
export type PipelineId = string;
export type PipelineLabel = string;
export type Reason1 = string | null;
export type Paused = PausedPipeline[];
export type RunningNow = number;

/**
 * Decision 4: what the executor already records, counted over the window.
 */
export interface SchedulerHealth {
  skipped: Skipped;
  missed: Missed;
  refused?: Refused;
  paused?: Paused;
  running_now: RunningNow;
}
export interface RefusalCount {
  reason: Reason;
  count: Count;
}
export interface PausedPipeline {
  pipeline_id: PipelineId;
  pipeline_label: PipelineLabel;
  reason?: Reason1;
}
