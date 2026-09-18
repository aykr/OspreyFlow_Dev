// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Label = string;
export type ConnectorProfile = string;
export type SourceLocation = string | null;
export type LegalBasis = string | null;

/**
 * What Connect (§2) actually collects: a connector choice and the
 * three mandatory gate answers. Nothing here is optional except
 * `legal_basis`'s presence at draft-creation time — a draft may be saved
 * mid-entry, but `StudioRecipeDraft.ready_for_profile` stays `False`
 * until all three are set, and §2 is explicit that Profile itself is
 * unreachable until they are.
 */
export interface ConnectDraftInput {
  label: Label;
  connector_profile: ConnectorProfile;
  source_location?: SourceLocation;
  handling?: Handling;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
export interface Handling {
  [k: string]: unknown;
}
