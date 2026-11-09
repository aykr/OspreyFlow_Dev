// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Kind = "api";
export type BaseUrl = string;
export type Auth = "none" | "bearer";
export type Secret = string | null;
export type Pagination = "none" | "page" | "next_link";
export type PageParam = string;
export type NextAt = string | null;
export type CaCertificate = string | null;

/**
 * An HTTP API: its base URL (HTTPS only), how it is signed in to, and how it pages. Its host
 * must be on the deployment's egress allow-list (`OSPREY_CONNECTOR_EGRESS`), which only an
 * operator changes: a host not on it is refused in words that say whom to ask.
 */
export interface ApiConnectionSettings {
  kind?: Kind;
  base_url: BaseUrl;
  auth?: Auth;
  secret?: Secret;
  pagination?: Pagination;
  page_param?: PageParam;
  next_at?: NextAt;
  ca_certificate?: CaCertificate;
}
