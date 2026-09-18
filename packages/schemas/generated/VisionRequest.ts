// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type DocumentId = string;
export type Image = string;
export type Text = string;
export type Model = string;

export interface VisionRequest {
  document_id: DocumentId;
  image: Image;
  text: Text;
  json_schema: JsonSchema;
  model: Model;
  [k: string]: unknown;
}
export interface JsonSchema {
  [k: string]: unknown;
}
