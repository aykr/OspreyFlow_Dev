// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Ok = boolean;
export type Words = string;

/**
 * *Test connection*: whether it could be read, in words; nothing read is returned.
 */
export interface ConnectionTest {
  ok: Ok;
  words: Words;
  [k: string]: unknown;
}
