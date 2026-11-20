// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Roles = string[];
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

/**
 * One typed model's answer to the check's one call, in fixed words, by the jobs it was typed
 * for: never the typed name, which may be a key pasted in the wrong field (owner's ruling 22).
 */
export interface ModelCheck {
  roles: Roles;
  outcome: Outcome;
  ok: Ok;
  words: Words;
  [k: string]: unknown;
}
