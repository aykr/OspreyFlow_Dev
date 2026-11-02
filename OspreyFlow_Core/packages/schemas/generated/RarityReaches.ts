// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "shared_attribute_rarity";
export type Reaches = number;
export type Scope = "dataset" | "case";

/**
 * "When the shared-attribute rarity between the subject and another of its type reaches X":
 * worked out over what the rule's author may see, per dataset or across the case's datasets.
 */
export interface RarityReaches {
  kind?: Kind;
  reaches: Reaches;
  scope?: Scope;
  [k: string]: unknown;
}
