// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type MigrationId = string;
export type AppliedEntityTypes = string[];
export type AppliedEdgeTypes = string[];
export type IndexesCreated = string[];
export type Reversible = boolean;

export interface SchemaReport {
  migration_id: MigrationId;
  applied_entity_types: AppliedEntityTypes;
  applied_edge_types: AppliedEdgeTypes;
  indexes_created: IndexesCreated;
  reversible?: Reversible;
  [k: string]: unknown;
}
