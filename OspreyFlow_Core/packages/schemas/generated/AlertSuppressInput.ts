// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Until = string;
export type Reason = string;

/**
 * *Suppress until…* (ADR-146 Amendment 1): a reason and the last day, at most 90 days ahead
 * (checked at the route against today). Only the team's lead, or its cover while the cover lasts,
 * may suppress one of the team's alerts.
 */
export interface AlertSuppressInput {
  until: Until;
  reason: Reason;
  [k: string]: unknown;
}
