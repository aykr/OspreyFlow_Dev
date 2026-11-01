// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Every = "daily" | "weekly";
export type Hour = number;
export type Weekday = number | null;

/**
 * When a scheduled rule runs (ADR-133 decision 1, stage (d)): every day, or every week on one
 * day, at a whole hour, read in Europe/London. A scheduled run judges what was stored over the
 * last day or the last week, as the rule's own author.
 */
export interface RuleSchedule {
  every?: Every;
  hour?: Hour;
  weekday?: Weekday;
  [k: string]: unknown;
}
