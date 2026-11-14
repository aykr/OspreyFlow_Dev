// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type Count = number | null;
export type Datasets = DatasetFilter[];
export type Earliest = string | null;
export type Latest = string | null;

export interface OfferedFilters {
  datasets: Datasets;
  dates: DateSpan | null;
  [k: string]: unknown;
}
export interface DatasetFilter {
  id: Id;
  name: Name;
  count: Count;
  [k: string]: unknown;
}
export interface DateSpan {
  earliest: Earliest;
  latest: Latest;
  [k: string]: unknown;
}
