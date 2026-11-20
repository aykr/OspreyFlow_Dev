// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Engine = string;
export type Ok = boolean;
export type Check = string | null;
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
export type Ok1 = boolean;
export type Words = string;
export type Models = ModelCheck[];
export type Words1 = string;

/**
 * The check's answer: `check` names a passed check for **Add**, `None` when anything was
 * refused (and then nothing of it is kept).
 */
export interface EngineCheckResult {
  engine: Engine;
  ok: Ok;
  check: Check;
  models: Models;
  words: Words1;
  [k: string]: unknown;
}
/**
 * One typed model's answer to the check's one call, in fixed words, by the jobs it was typed
 * for: never the typed name, which may be a key pasted in the wrong field (owner's ruling 22).
 */
export interface ModelCheck {
  roles: Roles;
  outcome: Outcome;
  ok: Ok1;
  words: Words;
  [k: string]: unknown;
}
