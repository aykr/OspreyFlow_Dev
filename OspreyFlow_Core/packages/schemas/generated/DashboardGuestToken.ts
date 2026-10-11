// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Token = string;
export type Uuid = string;
export type SupersetOrigin = string;

/**
 * A short-lived, read-only Superset guest token for one embedded dashboard.
 */
export interface DashboardGuestToken {
  token: Token;
  uuid: Uuid;
  superset_origin: SupersetOrigin;
  [k: string]: unknown;
}
