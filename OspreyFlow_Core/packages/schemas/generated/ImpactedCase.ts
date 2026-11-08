// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationId = string;
export type Name = string | null;

/**
 * A case reading the dataset (directly or through a composite) that the reader may open.
 * Cases they may not open are not listed and not counted (rule 7).
 */
export interface ImpactedCase {
  investigation_id: InvestigationId;
  name?: Name;
  [k: string]: unknown;
}
