// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "linked";
export type LinkType = string;
export type OtherType = string | null;

/**
 * Linked by a declared link type to something (of a declared type, or of any).
 */
export interface LinkedRelationship {
  kind?: Kind;
  link_type: LinkType;
  other_type?: OtherType;
  [k: string]: unknown;
}
