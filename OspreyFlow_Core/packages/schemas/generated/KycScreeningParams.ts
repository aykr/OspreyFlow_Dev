// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "kyc_screening";
export type MinScore = number;
export type ScreenOwners = boolean;
export type OwnerThreshold = number;

/**
 * ADR-109 phase F (the KYC addendum's Component 6): a newly loaded person or organisation
 * screened against the deployment's screening lists, and — for an organisation — each natural
 * person who ultimately owns at least `owner_threshold` of it, or controls it.
 */
export interface KycScreeningParams {
  typology?: Typology;
  min_score?: MinScore;
  screen_owners?: ScreenOwners;
  owner_threshold?: OwnerThreshold;
  [k: string]: unknown;
}
