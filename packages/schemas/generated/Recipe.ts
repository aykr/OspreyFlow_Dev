// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Id = string;
export type Version = number;
export type Label = string;
export type Profile = string;
export type Delimiter = string;
export type Encoding = string;
export type HeaderRows = number;
export type DateOrder = ("dmy" | "mdy") | null;
export type SourceCrs = string | null;
export type OntologyVersion = number;
export type LegalBasis = string | null;
export type Field = string | null;
export type Fields = string[] | null;
export type Transform = string | null;
export type Map = {
  [k: string]: string;
} | null;
export type Key = FieldBinding[];
export type Ref = string;
export type PoleClass = string;
export type Type = string;
export type MatchOn = string | null;
export type OnMatch = "reference" | "create";
export type Field1 = string;
export type Is = ("not_null" | "null") | null;
export type Handling1 = {
  [k: string]: unknown;
} | null;
export type Provenance1 = {
  [k: string]: unknown;
} | null;
export type Entities = RecipeEntity[];
export type Type1 = string;
export type From = string;
export type To = string;
export type Handling2 = {
  [k: string]: unknown;
} | null;
export type Provenance2 = {
  [k: string]: unknown;
} | null;
export type Edges = RecipeEdge[];
export type Field2 = string;
export type Action = "ignore";
export type Note = string | null;
export type UnmappedFields = UnmappedField[];
export type Cron = string | null;
export type Watch = string | null;

export interface Recipe {
  id: Id;
  version: Version;
  label: Label;
  connector: RecipeConnector;
  ontology_version: OntologyVersion;
  defaults?: RecipeDefaults;
  deduplicate?: DeduplicateConfig | null;
  row_template: RowTemplate;
  unmapped_fields?: UnmappedFields;
  schedule?: ScheduleConfig | null;
  [k: string]: unknown;
}
export interface RecipeConnector {
  profile: Profile;
  delimiter?: Delimiter;
  encoding?: Encoding;
  header_rows?: HeaderRows;
  date_order?: DateOrder;
  source_crs?: SourceCrs;
  [k: string]: unknown;
}
export interface RecipeDefaults {
  provenance?: Provenance;
  handling?: Handling;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
export interface Provenance {
  [k: string]: unknown;
}
export interface Handling {
  [k: string]: unknown;
}
export interface DeduplicateConfig {
  key: Key;
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
  [k: string]: unknown;
}
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
  handling?: Handling1;
  provenance?: Provenance1;
  [k: string]: unknown;
}
/**
 * A `when` clause — `09_INGEST_STUDIO.md` §4's conditional elements.
 */
export interface RecipeCondition {
  field: Field1;
  is?: Is;
  equals?: unknown;
  [k: string]: unknown;
}
export interface Properties {
  [k: string]: FieldBinding;
}
export interface RecipeEdge {
  type: Type1;
  from: From;
  to: To;
  when?: RecipeCondition | null;
  temporal?: TemporalBinding | null;
  properties?: Properties1;
  handling?: Handling2;
  provenance?: Provenance2;
  [k: string]: unknown;
}
export interface TemporalBinding {
  at: FieldBinding;
  [k: string]: unknown;
}
export interface Properties1 {
  [k: string]: FieldBinding;
}
export interface UnmappedField {
  field: Field2;
  action?: Action;
  note?: Note;
  [k: string]: unknown;
}
export interface ScheduleConfig {
  cron?: Cron;
  watch?: Watch;
  [k: string]: unknown;
}
