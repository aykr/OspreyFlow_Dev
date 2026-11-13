// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Band =
  | "identifier"
  | "name_exact"
  | "name_words"
  | "name_sounds"
  | "name_typo"
  | "mention_phrase"
  | "mention_words"
  | "mention_some";
export type Why = string;
export type Field = string | null;

export interface SearchMatch {
  band: Band;
  why: Why;
  field?: Field;
  [k: string]: unknown;
}
