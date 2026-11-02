// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "connection_strength";
export type LinkType = string | null;
export type OtherType = string | null;
export type Reaches = number;

/**
 * "When the connection strength between the subject and something it is linked to (by a
 * declared link type, or any; to a declared type, or anything) reaches X": the link's stored
 * weight with the influencers in force, as the rule's author may see it (rule 3).
 */
export interface StrengthReaches {
  kind?: Kind;
  link_type?: LinkType;
  other_type?: OtherType;
  reaches: Reaches;
  [k: string]: unknown;
}
