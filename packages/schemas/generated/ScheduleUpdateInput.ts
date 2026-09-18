// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type ScheduleCron = string | null;
export type ScheduleWatch = string | null;

/**
 * Body of `PATCH /v1/ingest/recipes/{id}/schedule` — §8's "schedule
 * it", kept separate from `publish` so changing when a recipe runs never
 * requires bumping its version or re-verifying a mapping that hasn't
 * changed.
 */
export interface ScheduleUpdateInput {
  schedule_cron?: ScheduleCron;
  schedule_watch?: ScheduleWatch;
  [k: string]: unknown;
}
