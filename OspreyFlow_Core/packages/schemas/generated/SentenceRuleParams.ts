// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Typology = "sentence";
export type PatternId = string;
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
export type Name = string;
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
export type MinScore = number;
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
export type Runs = "pre_commit" | "post_commit" | "schedule";
export type OnHit = "load" | "hold";
export type Scope = "just_me" | "this_case" | "deployment";
export type Every = "daily" | "weekly";
export type Hour = number;
export type Weekday = number | null;
export type MaxMatches = number;

/**
 * ADR-133 decision 1: the typology a sentence deploys as. `pattern_id` is its drawn pattern
 * (the subject, its equality conditions and a link: what the query builder draws), saved as the
 * author's and read afresh as them at each evaluation (ADR-036's discipline, as ADR-109 phase D's
 * `pattern` rule); `sentence` is the whole rule as written, and the source of what a pattern
 * cannot say. A run that would judge more than `max_matches` subjects is refused in words, never
 * judged in part (rule 2).
 */
export interface SentenceRuleParams {
  typology?: Typology;
  pattern_id: PatternId;
  sentence: RuleSentence;
  max_matches?: MaxMatches;
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
  schedule?: RuleSchedule | null;
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
  name?: Name;
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
  min_score?: MinScore;
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
/**
 * When a scheduled rule runs (ADR-133 decision 1, stage (d)): every day, or every week on one
 * day, at a whole hour, read in Europe/London. A scheduled run judges what was stored over the
 * last day or the last week, as the rule's own author.
 */
export interface RuleSchedule {
  every?: Every;
  hour?: Hour;
  weekday?: Weekday;
  [k: string]: unknown;
}
