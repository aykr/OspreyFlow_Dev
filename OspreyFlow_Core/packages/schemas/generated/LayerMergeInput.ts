// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * @minItems 1
 * @maxItems 5000
 */
export type ItemIds = [string, ...string[]];

export interface LayerMergeInput {
  item_ids: ItemIds;
}
