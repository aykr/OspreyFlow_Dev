// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DocumentId = string;
export type Locator = string;
export type ExcerptHash = string;
export type SourceRowKey = string | null;
export type SourceLoadId = string | null;

export interface SourceRef {
  document_id: DocumentId;
  locator: Locator;
  excerpt_hash: ExcerptHash;
  row_key?: SourceRowKey;
  load_id?: SourceLoadId;
  [k: string]: unknown;
}
