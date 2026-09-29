// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DocumentId = string;
export type Audio = string;
export type Language = string | null;
export type Diarize = boolean;
export type Model = string;

export interface TranscribeRequest {
  document_id: DocumentId;
  audio: Audio;
  language?: Language;
  diarize?: Diarize;
  model: Model;
  [k: string]: unknown;
}
