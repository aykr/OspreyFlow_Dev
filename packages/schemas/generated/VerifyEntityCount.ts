// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and _pending_port_placeholders.py, via generate_ts.py
export type Created = number;
export type Referenced = number;

/**
 * Per entity-type counts for one dry run — §5: "Counts. Nodes and
 * edges by type, how many referenced an existing node and how many
 * created one."
 */
export interface VerifyEntityCount {
  created?: Created;
  referenced?: Referenced;
  [k: string]: unknown;
}
