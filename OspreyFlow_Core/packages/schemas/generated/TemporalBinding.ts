// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Field = string | null;
export type Fields = string[] | null;
export type Transform = string | null;
export type Map = {
  [k: string]: string;
} | null;
export type Optional = boolean | null;

/**
 * A link's time. `at` is its start, or its only instant; `valid_to`, when bound, makes it a
 * span (ADR-127 decision 11): the end, read from a column of its own. An empty end cell is a span
 * still open (`Interval.valid_to` of `None`). Without `valid_to` the link is one instant, as
 * before: its end is its start.
 */
export interface TemporalBinding {
  at: FieldBinding;
  valid_to?: FieldBinding | null;
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
  field?: Field;
  fields?: Fields;
  literal?: unknown;
  transform?: Transform;
  map?: Map;
  optional?: Optional;
  [k: string]: unknown;
}
