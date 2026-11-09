// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Pack = ("fibo" | "niem" | "stix") | null;
export type HighestMarking = string;

/**
 * *New drawing board* with no case (Amendment 2 decision 5): a drawn dataset named after the
 * drawing, its home case and the board, in one step.
 */
export interface DrawingInput {
  name: Name;
  pack?: Pack;
  highest_marking: HighestMarking;
}
