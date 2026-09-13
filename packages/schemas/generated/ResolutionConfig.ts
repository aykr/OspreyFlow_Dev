// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py and _pending_port_placeholders.py, via generate_ts.py
export type Blocking = string[];
export type Comparisons = string[];

/**
 * Splink blocking/comparison rules per entity type — `01_DOMAIN_MODEL.md`
 * §4. Consumed by `services/resolve` from Phase 6 on; carried here because
 * it is part of the ontology's per-type shape.
 */
export interface ResolutionConfig {
  blocking?: Blocking;
  comparisons?: Comparisons;
  [k: string]: unknown;
}
