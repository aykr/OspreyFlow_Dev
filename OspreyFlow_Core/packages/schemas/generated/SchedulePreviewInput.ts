// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Cron = string;
export type Timezone = string | null;
export type After = string | null;

/**
 * Body of `POST /v1/ingest/schedule-preview` (ADR-110 decision 7): a schedule to explain
 * before it is saved. `after` defaults to now.
 */
export interface SchedulePreviewInput {
  cron: Cron;
  timezone?: Timezone;
  after?: After;
  [k: string]: unknown;
}
