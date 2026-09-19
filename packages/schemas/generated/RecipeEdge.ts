// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Type = string;
export type From = string;
export type To = string;
export type Field = string;
export type Is = ("not_null" | "null") | null;
export type Field1 = string | null;
export type Fields = string[] | null;
export type Transform = string | null;
export type Map = {
  [k: string]: string;
} | null;
export type Handling = {
  [k: string]: unknown;
} | null;
export type Provenance = {
  [k: string]: unknown;
} | null;

export interface RecipeEdge {
  type: Type;
  from: From;
  to: To;
  when?: RecipeCondition | null;
  temporal?: TemporalBinding | null;
  properties?: Properties;
  handling?: Handling;
  provenance?: Provenance;
  [k: string]: unknown;
}
/**
 * A `when` clause — `09_INGEST_STUDIO.md` §4's conditional elements.
 */
export interface RecipeCondition {
  field: Field;
  is?: Is;
  equals?: unknown;
  [k: string]: unknown;
}
export interface TemporalBinding {
  at: FieldBinding;
  [k: string]: unknown;
}
/**
 * One property's source: a source field (optionally passed through a
 * Knowledge Adapter `transform`), a `literal`, or a value `map` — never
 * an expression (`09_INGEST_STUDIO.md` §4: "no expression language").
 *
 * `fields` is the multi-column alternative to `field`, for a transform
 * that genuinely needs more than one source value — a coordinate pair,
 * or a British National Grid reference split across a letter pair and
 * two numeric columns. It is still one declared transform over named
 * source columns, not an expression: nothing computes which fields to
 * combine, the recipe states them outright. How many columns a given
 * transform takes is the adapter's own declared arity
 * (`knowledge_adapters.ARITY`), not a fixed count here — two is not
 * special, it is just what a coordinate pair happens to need.
 */
export interface FieldBinding {
  field?: Field1;
  fields?: Fields;
  literal?: unknown;
  transform?: Transform;
  map?: Map;
  [k: string]: unknown;
}
export interface Properties {
  [k: string]: FieldBinding;
}
