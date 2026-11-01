// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Params =
  | StructuringParams
  | RapidMovementParams
  | CircularFlowParams
  | KycScreeningParams
  | SharedAttributesParams
  | DocumentVerificationParams
  | PatternRuleParams
  | SentenceRuleParams;
export type Typology = "structuring";
export type Threshold = number;
export type WindowDays = number;
export type MinimumCount = number;
export type Typology1 = "rapid_movement";
export type WithinHours = number;
export type KeepFraction = number;
export type Typology2 = "circular_flow";
export type MaxHops = number;
export type WindowDays1 = number;
export type Typology3 = "kyc_screening";
export type MinScore = number;
export type ScreenOwners = boolean;
export type OwnerThreshold = number;
export type Typology4 = "shared_attributes";
export type MinOthers = number;
/**
 * @minItems 1
 */
export type Kinds = ["msisdn" | "email" | "ip" | "handle", ...("msisdn" | "email" | "ip" | "handle")[]];
export type Typology5 = "document_verification";
export type Typology6 = "pattern";
export type PatternId = string;
export type MaxMatches = number;
export type Typology7 = "sentence";
export type PatternId1 = string;
export type Subject = string;
/**
 * @maxItems 5
 */
export type Conditions =
  | []
  | [EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition]
  | [
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition
    ]
  | [
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition
    ]
  | [
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition
    ]
  | [
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition,
      EqualsCondition | OneOfCondition | AboveCondition | BelowCondition | WithinAreaCondition | WithinTimeCondition
    ];
export type Op = "equals";
export type Property = string;
export type Value = string;
export type Op1 = "one_of";
export type Property1 = string;
/**
 * @minItems 2
 * @maxItems 20
 */
export type Values =
  | [string, string]
  | [string, string, string]
  | [string, string, string, string]
  | [string, string, string, string, string]
  | [string, string, string, string, string, string]
  | [string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [string, string, string, string, string, string, string, string, string, string, string, string, string, string]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ]
  | [
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string,
      string
    ];
export type Op2 = "above";
export type Property2 = string;
export type Value1 = number;
export type Op3 = "below";
export type Property3 = string;
export type Value2 = number;
export type Op4 = "within_area";
export type Property4 = string;
export type Name1 = string;
/**
 * @minItems 3
 * @maxItems 64
 */
export type Points = [AreaPoint, AreaPoint, AreaPoint, ...AreaPoint[]];
export type Lon = number;
export type Lat = number;
export type Op5 = "within_time";
export type Property5 = string;
export type Start = string | null;
export type End = string | null;
export type Relationship =
  | (
      | LinkedRelationship
      | WithinStepsRelationship
      | AtLocationRelationship
      | OnHotlistRelationship
      | OnScreeningListRelationship
    )
  | null;
export type Kind = "linked";
export type LinkType = string;
export type OtherType = string | null;
export type Kind1 = "within_steps";
export type Steps = number;
export type OtherType1 = string;
export type Kind2 = "at_location";
export type LinkType1 = string;
export type Kind3 = "on_hotlist";
export type Kind4 = "on_screening_list";
export type MinScore1 = number;
export type Frequency = (CountFrequency | AmountFrequency | FirstTimeFrequency) | null;
export type Kind5 = "count";
export type LinkType2 = string;
export type AtLeast = number;
export type WithinDays = number;
export type Kind6 = "amount";
export type LinkType3 = string;
export type AmountProperty = string;
export type Over = number;
export type WithinDays1 = number;
export type Kind7 = "first_time";
export type LinkType4 = string;
export type Severity = "low" | "medium" | "high";
export type Team = "case" | "my_team";
export type Runs = "pre_commit" | "post_commit";
export type OnHit = "load" | "hold";
export type Scope = "just_me" | "this_case" | "deployment";
export type MaxMatches1 = number;
export type Trigger = "pre_commit" | "post_commit";
export type BudgetMs = number;

/**
 * What a case Author deploys (ADR-109 ruling 4): a typology with its parameters and the
 * trigger point it runs at. `budget_ms` bounds a pre-commit evaluation; overrunning it holds the
 * rows it could not judge (ruling 1, fail closed).
 */
export interface TypologyRuleInput {
  name: Name;
  params: Params;
  trigger?: Trigger;
  budget_ms?: BudgetMs;
  [k: string]: unknown;
}
export interface StructuringParams {
  typology?: Typology;
  threshold: Threshold;
  window_days: WindowDays;
  minimum_count: MinimumCount;
  [k: string]: unknown;
}
export interface RapidMovementParams {
  typology?: Typology1;
  within_hours: WithinHours;
  keep_fraction: KeepFraction;
  [k: string]: unknown;
}
export interface CircularFlowParams {
  typology?: Typology2;
  max_hops: MaxHops;
  window_days: WindowDays1;
  [k: string]: unknown;
}
/**
 * ADR-109 phase F (the KYC addendum's Component 6): a newly loaded person or organisation
 * screened against the deployment's screening lists, and — for an organisation — each natural
 * person who ultimately owns at least `owner_threshold` of it, or controls it.
 */
export interface KycScreeningParams {
  typology?: Typology3;
  min_score?: MinScore;
  screen_owners?: ScreenOwners;
  owner_threshold?: OwnerThreshold;
  [k: string]: unknown;
}
/**
 * Component 6's synthetic-identity check: a new customer's phone, email, IP address or handle
 * already used by at least `min_others` other customers.
 */
export interface SharedAttributesParams {
  typology?: Typology4;
  min_others?: MinOthers;
  kinds?: Kinds;
  [k: string]: unknown;
}
/**
 * Component 7: a new customer with no valid verifying document — none, or each one expired
 * or marked fraudulent.
 */
export interface DocumentVerificationParams {
  typology?: Typology5;
  [k: string]: unknown;
}
/**
 * ADR-109 phase D, the no-code typology builder: a sub-graph drawn in the query builder and
 * saved (a `SavedPattern` the deployer owns, read afresh at each evaluation — ADR-036's own
 * discipline for monitors), deployed as a rule. Matched against the stored graph, so it runs
 * after commit only. A match larger than `max_matches` nodes is refused in words, never alerted on
 * in part (rule 2).
 */
export interface PatternRuleParams {
  typology?: Typology6;
  pattern_id: PatternId;
  max_matches?: MaxMatches;
  [k: string]: unknown;
}
/**
 * ADR-133 decision 1: the typology a sentence deploys as. `pattern_id` is its drawn pattern
 * (the subject, its equality conditions and a link: what the query builder draws), saved as the
 * author's and read afresh as them at each evaluation (ADR-036's discipline, as ADR-109 phase D's
 * `pattern` rule); `sentence` is the whole rule as written, and the source of what a pattern
 * cannot say. A run that would judge more than `max_matches` subjects is refused in words, never
 * judged in part (rule 2).
 */
export interface SentenceRuleParams {
  typology?: Typology7;
  pattern_id: PatternId1;
  sentence: RuleSentence;
  max_matches?: MaxMatches1;
  [k: string]: unknown;
}
/**
 * The whole sentence: "When a <subject> [whose …] [linked by …] [N or more times in D days],
 * raise a <severity> alert for <team>, <runs>; for <scope>." The checks here are the ones that
 * need no ontology; `check_sentence` does the rest.
 */
export interface RuleSentence {
  subject: Subject;
  conditions?: Conditions;
  relationship?: Relationship;
  frequency?: Frequency;
  severity?: Severity;
  team?: Team;
  runs?: Runs;
  on_hit?: OnHit;
  scope?: Scope;
  [k: string]: unknown;
}
export interface EqualsCondition {
  op?: Op;
  property: Property;
  value: Value;
  [k: string]: unknown;
}
export interface OneOfCondition {
  op?: Op1;
  property: Property1;
  values: Values;
  [k: string]: unknown;
}
export interface AboveCondition {
  op?: Op2;
  property: Property2;
  value: Value1;
  [k: string]: unknown;
}
export interface BelowCondition {
  op?: Op3;
  property: Property3;
  value: Value2;
  [k: string]: unknown;
}
/**
 * The subject's own place inside a drawn area: a property that names a geometry (a
 * `Location`'s `geometry_ref`).
 */
export interface WithinAreaCondition {
  op?: Op4;
  property: Property4;
  area: DrawnArea;
  [k: string]: unknown;
}
/**
 * A drawn area: a closed outline of three to sixty-four corners, in order, the last joined
 * back to the first. `name` is what the sentence calls it ("the port area"), never matched on.
 */
export interface DrawnArea {
  name?: Name1;
  points: Points;
  [k: string]: unknown;
}
export interface AreaPoint {
  lon: Lon;
  lat: Lat;
  [k: string]: unknown;
}
/**
 * A date or time property within a window; either end may be open, not both.
 */
export interface WithinTimeCondition {
  op?: Op5;
  property: Property5;
  start?: Start;
  end?: End;
  [k: string]: unknown;
}
/**
 * Linked by a declared link type to something (of a declared type, or of any).
 */
export interface LinkedRelationship {
  kind?: Kind;
  link_type: LinkType;
  other_type?: OtherType;
  [k: string]: unknown;
}
/**
 * Within N steps of something of a declared type, by any links the author may see.
 */
export interface WithinStepsRelationship {
  kind?: Kind1;
  steps: Steps;
  other_type: OtherType1;
  [k: string]: unknown;
}
/**
 * Linked by a declared link type to a `Location` whose place is inside a drawn area.
 */
export interface AtLocationRelationship {
  kind?: Kind2;
  link_type: LinkType1;
  area: DrawnArea;
  [k: string]: unknown;
}
/**
 * The subject's identifier is on one of the author's own active hotlists (ADR-038).
 */
export interface OnHotlistRelationship {
  kind?: Kind3;
  [k: string]: unknown;
}
/**
 * The subject's name screens against the deployment's screening lists (ADR-109 phase F's
 * `screen`, reused): a person or an organisation only.
 */
export interface OnScreeningListRelationship {
  kind?: Kind4;
  min_score?: MinScore1;
  [k: string]: unknown;
}
/**
 * N or more events of a declared link type within D days.
 */
export interface CountFrequency {
  kind?: Kind5;
  link_type: LinkType2;
  at_least: AtLeast;
  within_days: WithinDays;
  [k: string]: unknown;
}
/**
 * A total of a declared amount on a link type's events over X within D days.
 */
export interface AmountFrequency {
  kind?: Kind6;
  link_type: LinkType3;
  amount_property: AmountProperty;
  over: Over;
  within_days: WithinDays1;
  [k: string]: unknown;
}
/**
 * The subject's first event of a declared link type, ever (as the author may see them).
 */
export interface FirstTimeFrequency {
  kind?: Kind7;
  link_type: LinkType4;
  [k: string]: unknown;
}
