// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py and _pending_port_placeholders.py, via generate_ts.py
export type CreatedAt = string;
export type PrincipalId = string;
export type Revision = number;
export type NodeId = string;

export interface AuditStub {
  created_at: CreatedAt;
  created_by: PrincipalId;
  revision?: Revision;
  superseded_by?: NodeId | null;
  [k: string]: unknown;
}
