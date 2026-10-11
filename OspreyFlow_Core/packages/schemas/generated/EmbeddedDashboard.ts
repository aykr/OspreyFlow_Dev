// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Slug = string;
export type Title = string;

/**
 * A Superset dashboard this person may open inside the Glass (ADR-111 Amendment 3).
 */
export interface EmbeddedDashboard {
  slug: Slug;
  title: Title;
  [k: string]: unknown;
}
