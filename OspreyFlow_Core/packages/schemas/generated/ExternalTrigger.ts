// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RunId = string;
export type PipelineLabel = string;
export type ServiceIdentity = string;
export type RanAsName = string;
export type StartedAt = string;
export type Outcome = string;
export type WallMs = number | null;
export type Withheld = boolean;

/**
 * Decision 14: an external trigger, with its service identity, who it ran as, and its cost.
 */
export interface ExternalTrigger {
  run_id: RunId;
  pipeline_label: PipelineLabel;
  service_identity: ServiceIdentity;
  ran_as_name: RanAsName;
  started_at: StartedAt;
  outcome: Outcome;
  wall_ms?: WallMs;
  withheld?: Withheld;
}
