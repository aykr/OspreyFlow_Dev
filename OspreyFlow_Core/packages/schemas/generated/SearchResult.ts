// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeIds = string[];
export type Type = string;
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
export type Text = string;
export type Match = boolean;
export type Passage = PassagePart[];
export type Date = string | null;
export type Datasets = string[];
export type IsDocument = boolean;

export interface SearchResult {
  node_ids: NodeIds;
  type: Type;
  match: SearchMatch;
  passage?: Passage;
  date?: Date;
  datasets?: Datasets;
  is_document: IsDocument;
  [k: string]: unknown;
}
export interface SearchMatch {
  band: Band;
  why: Why;
  field?: Field;
  [k: string]: unknown;
}
export interface PassagePart {
  text: Text;
  match: Match;
  [k: string]: unknown;
}
