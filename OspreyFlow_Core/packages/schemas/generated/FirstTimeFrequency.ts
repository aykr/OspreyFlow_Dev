// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "first_time";
export type LinkType = string;

/**
 * The subject's first event of a declared link type, ever (as the author may see them).
 */
export interface FirstTimeFrequency {
  kind?: Kind;
  link_type: LinkType;
  [k: string]: unknown;
}
