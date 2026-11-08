// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Pack = ("fibo" | "niem" | "stix") | null;
export type HighestMarking = string;

/**
 * `POST /v1/datasets/drawn` (ADR-143 Amendment 2 decision 5; ADR-140 Amendment 9 decision 2):
 * *New drawing board* with no case makes, in one step, a dataset of kind `drawn` named after the
 * drawing, its domain model live at version 1 (the starter pack chosen, or the POLE core alone),
 * and its home case, with the maker as its Author. The board itself is L3.3's.
 */
export interface DrawnDatasetInput {
  name: Name;
  pack?: Pack;
  highest_marking: HighestMarking;
}
