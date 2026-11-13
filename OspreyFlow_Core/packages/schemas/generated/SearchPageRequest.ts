// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Query = string;
export type Limit = number;
export type Group = string | null;
export type Datasets = string[] | null;
export type DateFrom = string | null;
export type DateTo = string | null;
export type Page = number;
export type PageSize = number | null;

/**
 * Today's request (`query`, `limit`), with the results page's fields beside it.
 */
export interface SearchPageRequest {
  query: Query;
  limit?: Limit;
  group?: Group;
  filters?: SearchFilters;
  page?: Page;
  page_size?: PageSize;
  [k: string]: unknown;
}
export interface SearchFilters {
  datasets?: Datasets;
  date_from?: DateFrom;
  date_to?: DateTo;
  [k: string]: unknown;
}
