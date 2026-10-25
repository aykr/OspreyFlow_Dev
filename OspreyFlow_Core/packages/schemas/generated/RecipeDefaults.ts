// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type LegalBasis = string | null;
export type Units = string[];

export interface RecipeDefaults {
  provenance?: Provenance;
  handling?: Handling;
  legal_basis?: LegalBasis;
  units?: Units;
  handling_columns?: HandlingColumns;
  [k: string]: unknown;
}
export interface Provenance {
  [k: string]: unknown;
}
export interface Handling {
  [k: string]: unknown;
}
export interface HandlingColumns {
  [k: string]: string;
}
