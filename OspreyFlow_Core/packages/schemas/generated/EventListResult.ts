// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Total = number;
export type EventId = string;
export type EdgeId = string;
export type EdgeType = string;
export type NodeId = string;
export type OccurredAt = string;
export type DurationS = number | null;
export type CellSite = string | null;
export type Lat = number | null;
export type Lon = number | null;
export type Direction = string | null;
export type InvestigationScope = string;
export type Classification = string;
export type HandlingCode = string;
export type ActionCode = string | null;
export type SanitisationCode = string | null;
export type OrgUnitId = string;
export type ReviewDate = string | null;
export type LegalBasis = string | null;
export type LoadId = string | null;
export type Events = EventRecord[];

export interface EventListResult {
  total: Total;
  events?: Events;
  [k: string]: unknown;
}
/**
 * One row in the analytics store. `edge_id` ties it back to the
 * summarised graph edge it is one occurrence of; `handling` is carried
 * per row (not looked up via `edge_id`) so a filtered query never has to
 * join back to the graph store to know what it may not show.
 */
export interface EventRecord {
  event_id: EventId;
  edge_id: EdgeId;
  edge_type: EdgeType;
  source_id: NodeId;
  target_id: NodeId;
  occurred_at: OccurredAt;
  duration_s?: DurationS;
  cell_site?: CellSite;
  lat?: Lat;
  lon?: Lon;
  direction?: Direction;
  properties?: Properties;
  investigation_scope: InvestigationScope;
  handling: Handling;
  load_id?: LoadId;
  [k: string]: unknown;
}
export interface Properties {
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
