// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NodeId = string;
export type Title = string | null;
export type DocumentKind = string | null;
export type ExpiresOn = string | null;
export type State = "valid" | "expired" | "fraudulent";

/**
 * A document verifying a customer, and whether it still does.
 */
export interface KycDocument {
  node_id: NodeId;
  title?: Title;
  document_kind?: DocumentKind;
  expires_on?: ExpiresOn;
  state: State;
  [k: string]: unknown;
}
