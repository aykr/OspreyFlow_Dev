// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "dormant_reactivated";
export type DormantDays = number;

/**
 * An account moving money again after at least `dormant_days` days without a movement. An
 * account with no movement before is new, not dormant.
 */
export interface DormantReactivatedParams {
  typology?: Typology;
  dormant_days?: DormantDays;
  [k: string]: unknown;
}
