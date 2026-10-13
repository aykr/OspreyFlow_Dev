// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Cron = string;
export type Timezone = string | null;

/**
 * The Admin area's *Change schedule* (ADR-110 Amendment 3): a new time, the owner kept.
 */
export interface ChangeScheduleInput {
  cron: Cron;
  timezone?: Timezone;
  [k: string]: unknown;
}
