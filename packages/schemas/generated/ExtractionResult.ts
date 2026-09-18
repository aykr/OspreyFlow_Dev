// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type DocumentId = string;
export type Model = string;

export interface ExtractionResult {
  document_id: DocumentId;
  model: Model;
  data: Data;
  [k: string]: unknown;
}
export interface Data {
  [k: string]: unknown;
}
