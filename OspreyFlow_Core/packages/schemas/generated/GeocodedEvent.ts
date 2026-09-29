// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type EventId = string;
export type EdgeId = string;
export type EdgeType = string;
export type NodeId = string;
export type OccurredAt = string;
export type GeometryRef = string;
export type Value = string;
export type PreviousValue = string | null;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;

/**
 * One event the request covered, with what its `property` held before this call.
 * `previous_value == value` means the call changed nothing for that event, which is how a caller
 * keeps a redraw idempotent.
 */
export interface GeocodedEvent {
  event_id: EventId;
  edge_id: EdgeId;
  edge_type: EdgeType;
  source_id: NodeId;
  target_id: NodeId;
  occurred_at: OccurredAt;
  geometry_ref: GeometryRef;
  value: Value;
  previous_value?: PreviousValue;
  handling: Handling;
  [k: string]: unknown;
}
export interface Handling {
  classification: Classification;
  handling_code: HandlingCode;
  action_code?: ActionCode;
  sanitisation_code?: SanitisationCode;
  originator: OrgUnitId;
  owning_unit: OrgUnitId;
  review_date?: ReviewDate;
  legal_basis?: LegalBasis;
  [k: string]: unknown;
}
