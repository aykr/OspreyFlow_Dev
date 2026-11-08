// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
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
export type PackVersions = {
  [k: string]: number;
} | null;
export type ModelVersion = number | null;
export type LegalBasis = string | null;
export type Units = string[];
export type Field = string | null;
export type Fields = string[] | null;
export type Transform = string | null;
export type Map = {
  [k: string]: string;
} | null;
export type Optional = boolean | null;
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
export type Kind = "message_text" | "document_text" | "image_file" | "video_file";
export type Field2 = string;
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
export type Field3 = string;
export type Action = "ignore";
export type Note = string | null;
export type UnmappedFields = UnmappedField[];
export type Cron = string | null;
export type Watch = string | null;
export type Id1 = string;
/**
 * The pipeline graph's closed node vocabulary (`06_DECISIONS.md` ADR-108). Closed on
 * purpose: rule 8 — no expression or scripting language in the Studio; every node is a declared
 * stage whose transforms remain Knowledge Adapters with golden files.
 */
export type PipelineNodeKind = "domain_model" | "source" | "profile" | "map" | "extract" | "enrich" | "load";
export type Label1 = string;
export type Nodes = PipelineNode[];
export type Source = string;
export type Target = string;
export type Edges1 = PipelineEdge[];
export type Staging = (LookupStep | JoinStep | FilterStep | DeriveStep | UnionStep | DedupeStep)[] | null;
export type Id2 = string;
export type Label2 = string | null;
export type Kind1 = "lookup";
export type Input = string;
export type List = string;
export type On = string;
export type Normalise = string | null;
/**
 * @minItems 1
 */
export type Add = [AddedColumn, ...AddedColumn[]];
export type Column = string;
export type As = string | null;
export type Id3 = string;
export type Label3 = string | null;
export type Kind2 = "join";
export type Left = string;
export type Right = string;
export type LeftKey = string;
export type RightKey = string;
export type Normalise1 = string | null;
export type How = "inner" | "left";
/**
 * @minItems 1
 */
export type Add1 = [AddedColumn, ...AddedColumn[]];
export type Id4 = string;
export type Label4 = string | null;
export type Kind3 = "filter";
export type Input1 = string;
/**
 * @minItems 1
 */
export type Keep = [FilterCondition, ...FilterCondition[]];
export type Field4 = string;
export type Is1 = ("not_null" | "null") | null;
export type Equals1 = string | null;
export type In = [string, ...string[]] | null;
export type Id5 = string;
export type Label5 = string | null;
export type Kind4 = "derive";
export type Input2 = string;
export type Column1 = string;
export type Operation = "concat" | "split" | "substring" | "date_parse" | "arithmetic" | "case_when" | "normalise";
/**
 * @minItems 1
 */
export type Columns = [string, ...string[]];
export type Id6 = string;
export type Label6 = string | null;
export type Kind5 = "union";
/**
 * @minItems 2
 */
export type Inputs = [string, string, ...string[]];
export type Id7 = string;
export type Label7 = string | null;
export type Kind6 = "dedupe";
export type Input3 = string;
/**
 * @minItems 1
 */
export type On1 = [string, ...string[]];

export interface Recipe {
  id: Id;
  version: Version;
  label: Label;
  connector: RecipeConnector;
  ontology_version: OntologyVersion;
  pack_versions?: PackVersions;
  model_version?: ModelVersion;
  defaults?: RecipeDefaults;
  deduplicate?: DeduplicateConfig | null;
  row_template: RowTemplate;
  unmapped_fields?: UnmappedFields;
  schedule?: ScheduleConfig | null;
  pipeline?: PipelineGraph | null;
  staging?: Staging;
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
  units?: Units;
  handling_columns?: HandlingColumns;
  [k: string]: unknown;
}
export interface Provenance {
  [k: string]: unknown;
}
export interface Handling {
  [k: string]: unknown;
}
export interface HandlingColumns {
  [k: string]: string;
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
  optional?: Optional;
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
  content?: ContentBinding | null;
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
  handling?: Handling2;
  provenance?: Provenance2;
  [k: string]: unknown;
}
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
export interface Properties1 {
  [k: string]: FieldBinding;
}
export interface UnmappedField {
  field: Field3;
  action?: Action;
  note?: Note;
  [k: string]: unknown;
}
export interface ScheduleConfig {
  cron?: Cron;
  watch?: Watch;
  [k: string]: unknown;
}
/**
 * ADR-108: the recipe as a typed DAG. A v1 recipe that has none is read as its canonical
 * chain (`pipeline_from_recipe`), derived at read time and never stored back.
 */
export interface PipelineGraph {
  nodes?: Nodes;
  edges?: Edges1;
  [k: string]: unknown;
}
/**
 * One stage of a pipeline. `config` carries the stage's own settings (a source node's
 * connector profile and location, a domain node's pack) — its keys are each stage's declared
 * vocabulary, validated by `services/ingest/pipeline.py`, never free code.
 */
export interface PipelineNode {
  id: Id1;
  kind: PipelineNodeKind;
  label: Label1;
  config?: Config;
  [k: string]: unknown;
}
export interface Config {
  [k: string]: unknown;
}
/**
 * A data dependency: `source` feeds `target`. The graph is acyclic (validated at save).
 */
export interface PipelineEdge {
  source: Source;
  target: Target;
  [k: string]: unknown;
}
/**
 * Add columns from a reference list on a key: every row of `input` is kept, and a row whose
 * key is not in the list keeps empty cells for the added columns (counted, never dropped). The
 * list is the dataset's own, or a screening list the dataset subscribes to (ADR-140 Amendment 9
 * decision 3); its key column is the list's own `key_column`.
 */
export interface LookupStep {
  id: Id2;
  label?: Label2;
  kind: Kind1;
  input: Input;
  list: List;
  on: On;
  normalise?: Normalise;
  add: Add;
}
/**
 * A column a Lookup or a Join brings across, optionally renamed.
 */
export interface AddedColumn {
  column: Column;
  as?: As;
}
/**
 * Join two tables on a declared key, never a guessed one (brief §6): exact, or each side read
 * through the same Knowledge Adapter first (E.164, prison number, IBAN…). A row of `left` with
 * several matches gives one row per match, each carrying both sides' refs.
 */
export interface JoinStep {
  id: Id3;
  label?: Label3;
  kind: Kind2;
  left: Left;
  right: Right;
  left_key: LeftKey;
  right_key: RightKey;
  normalise?: Normalise1;
  how?: How;
  add: Add1;
}
/**
 * Keep the rows for which every condition holds; the others are counted, not lost.
 */
export interface FilterStep {
  id: Id4;
  label?: Label4;
  kind: Kind3;
  input: Input1;
  keep: Keep;
}
/**
 * One declared condition on a column: exactly one of `is`, `equals` or `in`.
 */
export interface FilterCondition {
  field: Field4;
  is?: Is1;
  equals?: Equals1;
  in?: In;
}
/**
 * A new column from a catalogued operation over named columns (brief §6). `settings` are the
 * operation's declared settings (a separator, a part, a time zone…), data and never code; the
 * operation refuses a wrong one in words, as its golden file shows.
 */
export interface DeriveStep {
  id: Id5;
  label?: Label5;
  kind: Kind4;
  input: Input2;
  column: Column1;
  operation: Operation;
  columns: Columns;
  settings?: Settings;
}
export interface Settings {
  [k: string]: unknown;
}
/**
 * Stack tables with the same columns; each row keeps its own refs.
 */
export interface UnionStep {
  id: Id6;
  label?: Label6;
  kind: Kind5;
  inputs: Inputs;
}
/**
 * Drop repeats on declared columns (today's deduplication key, as a step). The first row in
 * the input's order stands for its repeats and carries all their refs, so the element it becomes
 * names every source row it stands for; the repeats are counted.
 */
export interface DedupeStep {
  id: Id7;
  label?: Label7;
  kind: Kind6;
  input: Input3;
  on: On1;
}
