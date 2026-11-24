// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type DatasetId = string;
export type Version = number;
export type State = "draft" | "live" | "previous";
export type Name = string;
export type Kind = "entity_type" | "link_type" | "property";
export type OnType = string | null;
export type AddedIn = number;
export type RetiredIn = number | null;
/**
 * The five-class upper ontology. Closed: a deployment may add entity
 * types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1.
 */
export type PoleClass = "person" | "object" | "location" | "event" | "organisation";
export type Identifiers = string[];
export type MatchOn = string;
export type OnMatch = "reference" | "create";
export type PropertyType = "string" | "string[]" | "date" | "datetime" | "integer" | "float" | "boolean" | "enum";
export type Indexed = boolean;
export type Extensions = ModelExtension[];
export type ReferenceLists = string[];
export type CreatedAt = string;
export type PrincipalId = string;
export type MadeLiveAt = string | null;
export type RevertedFrom = number | null;
export type Revision = string | null;

/**
 * One version of a dataset's domain model (R3, R12).
 */
export interface TargetModel {
  dataset_id: DatasetId;
  version: Version;
  state: State;
  packs?: Packs;
  extensions?: Extensions;
  reference_lists?: ReferenceLists;
  created_at: CreatedAt;
  created_by: PrincipalId;
  made_live_at?: MadeLiveAt;
  made_live_by?: PrincipalId | null;
  reverted_from?: RevertedFrom;
  revision?: Revision;
}
export interface Packs {
  [k: string]: number;
}
/**
 * A type or property the dataset's own model adds beyond the core and its packs (ADR-140
 * decision 4; today's analyst-proposed type, ADR-090). Retired, never deleted: a rename is "add
 * the new, retire the old".
 *
 * **An entity type's record** carries its class (one of the five POLE classes, closed), its
 * identifiers and its matching rule (ADR-140 Amendment 22 item 3). **A property's record**
 * names the type it is on, its value type and whether it is indexed (the ontology's own
 * `PropertyDef.indexed`). Every one of these is optional, so an extension saved before they
 * existed still reads (a type with no class says so on screen) and is never changed by reading
 * it; a field that belongs to the other kind is refused.
 */
export interface ModelExtension {
  name: Name;
  kind: Kind;
  on_type?: OnType;
  added_in: AddedIn;
  retired_in?: RetiredIn;
  pole_class?: PoleClass | null;
  identifiers?: Identifiers;
  matching?: MatchingRule | null;
  value_type?: PropertyType | null;
  indexed?: Indexed;
}
/**
 * A type's rule for when two records are the same (ADR-140 Amendment 22 item 3; the owner's
 * ruling of 21 November 2026: it lives on the type record, not on each pipeline's element).
 *
 * `match_on` is the field a record is found by and `on_match` what the engine does when it finds
 * one: the same two values the recipe engine takes today (`match_on` and `on_match`). A rule is
 * only as good as the matching code can make it: `match_on` must name one of the type's
 * identifiers or one of its indexed properties, because the store answers a lookup for those and
 * no others (`services/ingest/recipe_rules.py`, `reference_match_problems`). The store refuses a
 * rule that does not (`target_models._refuse_a_rule_a_reference_cannot_use`).
 */
export interface MatchingRule {
  match_on: MatchOn;
  on_match?: OnMatch;
}
