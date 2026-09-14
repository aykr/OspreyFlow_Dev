// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type Cron = string | null;
export type Watch = string | null;

export interface ScheduleConfig {
  cron?: Cron;
  watch?: Watch;
  [k: string]: unknown;
}
