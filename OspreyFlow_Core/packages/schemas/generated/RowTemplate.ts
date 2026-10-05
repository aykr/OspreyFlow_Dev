// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Ref = string;
export type PoleClass = string;
export type Type = string;
export type MatchOn = string | null;
export type OnMatch = "reference" | "create";
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
export type Kind = "message_text" | "document_text" | "image_file" | "video_file";
export type Field2 = string;
export type Entities = RecipeEntity[];
export type Type1 = string;
export type From = string;
export type To = string;
export type Handling1 = {
  [k: string]: unknown;
} | null;
export type Provenance1 = {
  [k: string]: unknown;
} | null;
export type Edges = RecipeEdge[];

export interface RowTemplate {
  entities: Entities;
  edges?: Edges;
  [k: string]: unknown;
}
export interface RecipeEntity {
  ref: Ref;
  pole_class: PoleClass;
  type: Type;
  match_on?: MatchOn;
  on_match?: OnMatch;
  when?: RecipeCondition | null;
  properties?: Properties;
  handling?: Handling;
  provenance?: Provenance;
  content?: ContentBinding | null;
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
export interface Properties {
  [k: string]: FieldBinding;
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
/**
 * ADR-094: a source column whose value the model can read. On a link it is the link's message
 * or document text, written to the link's event (never the graph link), where the reader and
 * extraction read it, as they read an Enron email's excerpt. A column named outright, never an
 * expression (rule 8).
 */
export interface ContentBinding {
  kind: Kind;
  field: Field2;
  [k: string]: unknown;
}
export interface RecipeEdge {
  type: Type1;
  from: From;
  to: To;
  when?: RecipeCondition | null;
  temporal?: TemporalBinding | null;
  properties?: Properties1;
  content?: ContentBinding | null;
  handling?: Handling1;
  provenance?: Provenance1;
  [k: string]: unknown;
}
export interface TemporalBinding {
  at: FieldBinding;
  [k: string]: unknown;
}
export interface Properties1 {
  [k: string]: FieldBinding;
}
