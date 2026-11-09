// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Drawn = string;
export type DrawnLabel = string;
export type Loaded = string;
export type LoadedLabel = string;
export type LoadedType = string;
export type Score = number;
export type Why = string;

/**
 * Step 2, *Match*: a drawn node and a loaded node of the target the reader may see, offered
 * as alike. Chosen, it is written as a scored, `inferred` `SAME_AS` with the merge (rule 5): a
 * person confirms it later, and nothing is collapsed in storage (rule 6).
 */
export interface MergeMatch {
  drawn: Drawn;
  drawn_label: DrawnLabel;
  loaded: Loaded;
  loaded_label: LoadedLabel;
  loaded_type: LoadedType;
  score: Score;
  why: Why;
}
