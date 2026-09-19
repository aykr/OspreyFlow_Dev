// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DocumentId = string;
export type Model = string;
export type Language = string;
export type Start = number;
export type End = number;
export type Text = string;
export type Speaker = string | null;
export type Start1 = number;
export type End1 = number;
export type Text1 = string;
export type Words = TranscriptWord[];
export type Segments = TranscriptSegment[];

export interface Transcript {
  document_id: DocumentId;
  model: Model;
  language: Language;
  segments: Segments;
  [k: string]: unknown;
}
export interface TranscriptSegment {
  start: Start;
  end: End;
  text: Text;
  speaker?: Speaker;
  words?: Words;
  [k: string]: unknown;
}
export interface TranscriptWord {
  start: Start1;
  end: End1;
  text: Text1;
  [k: string]: unknown;
}
