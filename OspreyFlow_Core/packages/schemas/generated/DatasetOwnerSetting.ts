// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type OwnersMayBe = "people_and_teams" | "people_only" | "teams_only";

/**
 * Admin › System's *Dataset owners may be* (ADR-145 Amendment 4 decision 7); it governs *Make
 * live* and *Change owner…*.
 */
export interface DatasetOwnerSetting {
  owners_may_be?: OwnersMayBe;
}
