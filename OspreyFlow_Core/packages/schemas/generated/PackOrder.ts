// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
/**
 * @maxItems 200
 */
export type ItemIds = string[];

/**
 * The reader's own visible items in their new order: the items withheld from them keep their
 * places.
 */
export interface PackOrder {
  item_ids: ItemIds;
  [k: string]: unknown;
}
