// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "node" | "link";
export type DrawnType = string;
export type TargetType = string | null;
export type Items = number;
export type WhyNot = string | null;
export type Choices = string[];
export type DrawnProperties = string[];

/**
 * Step 1, *Map the models* (ADR-143 Amendment 7, the owner's ruling): one drawn type and the
 * target's type its items go in as, proposed as the same name when the target's model holds it,
 * else `None` with why not. `choices` are every type of the target's live model of this kind,
 * any of which it may be mapped to, as a Studio load's Map step maps; `drawn_properties` the
 * properties its items carry. Counts only the items the reader may see.
 */
export interface TypeMapping {
  kind: Kind;
  drawn_type: DrawnType;
  target_type: TargetType;
  items: Items;
  why_not?: WhyNot;
  choices?: Choices;
  drawn_properties?: DrawnProperties;
}
