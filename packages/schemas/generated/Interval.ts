// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py and _pending_port_placeholders.py, via generate_ts.py
export type ValidFrom = string;
export type ValidTo = string | null;

export interface Interval {
  valid_from: ValidFrom;
  valid_to?: ValidTo;
  [k: string]: unknown;
}
