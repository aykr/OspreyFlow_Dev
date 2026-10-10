// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Label = string;
export type EntityTypes = string[];
export type EdgeTypes = string[];

/**
 * One domain model the Studio offers (ADR-108 phase D): the POLE core, or a pack with the
 * entity and link types it adds over it.
 */
export interface DomainPackEntry {
  name: Name;
  label: Label;
  entity_types?: EntityTypes;
  edge_types?: EdgeTypes;
  [k: string]: unknown;
}
