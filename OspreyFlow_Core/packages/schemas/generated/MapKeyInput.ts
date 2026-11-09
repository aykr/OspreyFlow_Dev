// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Key = string;

/**
 * `PUT /v1/admin/maps/providers/{id}/key`. Write-only: never echoed, logged or returned.
 */
export interface MapKeyInput {
  key: Key;
}
