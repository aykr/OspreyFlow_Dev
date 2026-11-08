// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Name = string;
export type OwningUnit = string;
export type Egress = "none" | "contracted" | "any";
export type HighestMarking = string | null;
export type Kind = "source" | "composite" | "drawn";
export type PromotionPolicy = "author_promotes" | "second_person_reviews";

/**
 * One dataset as the Admin area's Datasets screen shows it (ADR-136 decision 2): its name, the
 * unit that holds it, and its egress.
 */
export interface AdminDataset {
  id: Id;
  name: Name;
  owning_unit: OwningUnit;
  egress: Egress;
  highest_marking?: HighestMarking;
  kind?: Kind;
  promotion_policy?: PromotionPolicy;
  [k: string]: unknown;
}
