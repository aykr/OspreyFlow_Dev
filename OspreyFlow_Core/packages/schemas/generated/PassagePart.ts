// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Text = string;
export type Match = boolean;

export interface PassagePart {
  text: Text;
  match: Match;
  [k: string]: unknown;
}
