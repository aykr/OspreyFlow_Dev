// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Op = "add" | "subtract" | "multiply" | "divide";
export type Constant = string | null;

export interface ArithmeticSettings {
  op: Op;
  constant?: Constant;
}
