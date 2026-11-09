// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type ElementId = string;
export type ItemId = string;
export type WatchId = string | null;

/**
 * What declaring or linking wrote: the element's id, the board's item id, and the watch set.
 */
export interface DrawnItemMade {
  element_id: ElementId;
  item_id: ItemId;
  watch_id?: WatchId;
  [k: string]: unknown;
}
