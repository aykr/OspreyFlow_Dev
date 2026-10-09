// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Name = string;
export type Arity = number;
export type Parts = string[];

/**
 * One entry of the Knowledge Adapter catalogue Map's transform picker
 * reads from — `packages/knowledge_adapters.REGISTRY`/`ARITY`, never
 * hand-duplicated here. `arity` is `1` for every adapter absent from
 * `ARITY` (that module's own docstring: such an adapter "does not support
 * `fields` at all"), so the studio only ever offers a `fields` picker
 * with more than one slot for a transform that actually declared one.
 */
export interface TransformDescriptor {
  name: Name;
  arity: Arity;
  parts?: Parts;
  [k: string]: unknown;
}
