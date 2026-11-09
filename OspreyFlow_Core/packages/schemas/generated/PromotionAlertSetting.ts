// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type AlertAfterDays = number;

/**
 * Admin › Operations' *Alert the reviewers and administrators after N days* (ADR-145
 * decision 9; default 3).
 */
export interface PromotionAlertSetting {
  alert_after_days?: AlertAfterDays;
}
