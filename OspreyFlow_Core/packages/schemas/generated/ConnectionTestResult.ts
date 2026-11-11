// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Engine = string;
export type Outcome =
  | "ok"
  | "not_routed"
  | "gateway_token"
  | "key_refused"
  | "model_not_offered"
  | "model_not_enabled"
  | "sign_in_expired"
  | "request_refused"
  | "cooling_down"
  | "rate_limited"
  | "unreachable";
export type Ok = boolean;
export type Words = string;

export interface ConnectionTestResult {
  engine: Engine;
  outcome: Outcome;
  ok: Ok;
  words: Words;
  [k: string]: unknown;
}
