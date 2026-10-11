// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Justification = string | null;
export type OriginatorReference = string | null;

/**
 * An override, when an item needs its originator consulted: both, or the export is refused
 * (ADR-045/047, as for every export).
 */
export interface PackExportRequest {
  justification?: Justification;
  originator_reference?: OriginatorReference;
  [k: string]: unknown;
}
