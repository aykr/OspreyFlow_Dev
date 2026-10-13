// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type RecipeId = string;
export type Version = number;
/**
 * `09_INGEST_STUDIO.md` §6's `studio_recipes.status` values.
 */
export type StudioRecipeStatus = "draft" | "published" | "flagged" | "superseded";
export type Label = string;
export type ConnectorProfile = string | null;
export type SourceLocation = string | null;
export type LegalBasis = string | null;
export type OwningUnit = string;
export type PrincipalId = string;
export type CreatedByName = string | null;
export type CreatedAt = string;
export type ReadyForProfile = boolean;
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
export type Handling1 = {
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
export type Handling2 = {
  [k: string]: unknown;
} | null;
export type Provenance1 = {
  [k: string]: unknown;
} | null;
export type Edges = RecipeEdge[];
export type Field3 = string;
export type Action = "ignore";
export type Note = string | null;
export type UnmappedFields = UnmappedField[];
export type VerifiedAt = string | null;
export type OntologyVersion = number | null;
export type GitPath = string | null;
export type PublishedByName = string | null;
export type PublishedAt = string | null;
export type ScheduleCron = string | null;
export type ScheduleWatch = string | null;
export type ScheduleTimezone = string | null;
export type ScheduleSetAt = string | null;
export type SchedulePaused = boolean;
export type SchedulePausedReason = string | null;
export type DatasetId = string | null;
export type Id = string;
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

/**
 * The Connect-stage view of one `studio_recipes` row (§6) — not the
 * full `Recipe`, which does not exist until Map supplies a
 * `row_template` and Publish supplies a `git_path`.
 */
export interface StudioRecipeDraft {
  recipe_id: RecipeId;
  version: Version;
  status: StudioRecipeStatus;
  label: Label;
  connector_profile?: ConnectorProfile;
  source_location?: SourceLocation;
  handling?: Handling;
  legal_basis?: LegalBasis;
  owning_unit: OwningUnit;
  created_by: PrincipalId;
  created_by_name?: CreatedByName;
  created_at: CreatedAt;
  ready_for_profile: ReadyForProfile;
  row_template?: RowTemplate | null;
  unmapped_fields?: UnmappedFields;
  verified_at?: VerifiedAt;
  ontology_version?: OntologyVersion;
  git_path?: GitPath;
  published_by?: PrincipalId | null;
  published_by_name?: PublishedByName;
  published_at?: PublishedAt;
  schedule_cron?: ScheduleCron;
  schedule_watch?: ScheduleWatch;
  schedule_timezone?: ScheduleTimezone;
  schedule_owner?: PrincipalId | null;
  schedule_set_at?: ScheduleSetAt;
  schedule_paused?: SchedulePaused;
  schedule_paused_reason?: SchedulePausedReason;
  dataset_id?: DatasetId;
  pipeline?: PipelineGraph | null;
  [k: string]: unknown;
}
export interface Handling {
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
  handling?: Handling2;
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
export interface UnmappedField {
  field: Field3;
  action?: Action;
  note?: Note;
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
  id: Id;
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
