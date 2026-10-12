// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type InvestigationId = string;
export type Name = string | null;

export interface CaseEventHolder {
  investigation_id: InvestigationId;
  name?: Name;
  [k: string]: unknown;
}
