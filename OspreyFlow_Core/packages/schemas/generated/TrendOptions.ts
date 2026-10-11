// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Label = string;
export type Name1 = string;
export type Kind = "number" | "category";
export type Values = string[];
export type Fields = TrendFieldOption[];
export type EventTypes = TrendEventTypeOption[];

/**
 * What the builder may offer for this deployment's ontology: its temporal link types and,
 * for each, the properties a sum or a series may use.
 */
export interface TrendOptions {
  event_types: EventTypes;
  [k: string]: unknown;
}
export interface TrendEventTypeOption {
  name: Name;
  label: Label;
  fields?: Fields;
  [k: string]: unknown;
}
export interface TrendFieldOption {
  name: Name1;
  kind: Kind;
  values?: Values;
  [k: string]: unknown;
}
