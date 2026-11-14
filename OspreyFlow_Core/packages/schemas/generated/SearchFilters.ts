// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Datasets = string[] | null;
export type DateFrom = string | null;
export type DateTo = string | null;

export interface SearchFilters {
  datasets?: Datasets;
  date_from?: DateFrom;
  date_to?: DateTo;
  [k: string]: unknown;
}
