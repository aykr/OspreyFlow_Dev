// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Label = string;
export type Kind = "provider" | "gateway" | "bedrock";
export type Address = string | null;
export type AddressAsked = boolean;
export type Key = boolean;
export type Example = string | null;
export type Jobs = string[];
export type Prefix = string;
export type Note = string;

/**
 * One provider of *Admin › Models*' list (ADR-135 Amendment 14 point 1), as the form shows it:
 * its own address or that it asks one, whether it signs in by a key, its jobs alone, a current
 * model as the example beside the typed name, and LiteLLM's prefix, which the form takes off a
 * name typed with it. The hosts a check calls stay in the Conduit.
 */
export interface CatalogueEntry {
  id: Id;
  label: Label;
  kind: Kind;
  address: Address;
  address_asked: AddressAsked;
  key: Key;
  example: Example;
  jobs: Jobs;
  prefix: Prefix;
  note?: Note;
  [k: string]: unknown;
}
