// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Audience = "only_me" | "team";

/**
 * ADR-133 ruling 3: the owner's choice of who a hotlist's alerts reach.
 */
export interface HotlistAudienceInput {
  audience: Audience;
  [k: string]: unknown;
}
