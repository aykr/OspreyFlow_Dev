// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * `00_ARCHITECTURE.md` §1.2's worked example: "none | api_key_query |
 * api_key_header | bearer | basic | oauth2", named exactly.
 */
export type ProfileAuthType = "none" | "api_key_query" | "api_key_header" | "bearer" | "basic" | "oauth2";

export interface ProfileAuth {
  type: ProfileAuthType;
  [k: string]: unknown;
}
