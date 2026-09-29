// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ScheduleCron = string | null;
export type ScheduleWatch = string | null;

/**
 * Body of `POST /v1/ingest/recipes/{id}/publish` — schedule is
 * optional at publish time (a recipe may be published unscheduled, run
 * only on demand) and settable/changeable later via `ScheduleUpdateInput`
 * without republishing the mapping itself.
 */
export interface PublishRecipeInput {
  schedule_cron?: ScheduleCron;
  schedule_watch?: ScheduleWatch;
  [k: string]: unknown;
}
