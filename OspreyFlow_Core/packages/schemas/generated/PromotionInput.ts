// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * @minItems 1
 * @maxItems 500
 */
export type ItemIds = [string, ...string[]];

/**
 * The items ticked. Links, pictures and match decisions follow their items, and are listed
 * here only to say which of them go; each is checked again.
 */
export interface PromotionInput {
  item_ids: ItemIds;
}
