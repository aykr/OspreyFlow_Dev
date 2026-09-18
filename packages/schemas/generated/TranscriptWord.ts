// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Start = number;
export type End = number;
export type Text = string;

export interface TranscriptWord {
  start: Start;
  end: End;
  text: Text;
  [k: string]: unknown;
}
