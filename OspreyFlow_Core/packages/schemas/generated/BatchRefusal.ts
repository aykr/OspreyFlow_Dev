// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Code = "too_many_nodes" | "too_many_links" | "found_nothing" | "no_longer_an_editor" | "took_too_long";
export type CapKind = ("nodes" | "edges") | null;
export type Cap = number | null;
export type WouldBe = number | null;

/**
 * Why nothing was saved. For a result past the cap, the cap and the figure it would have
 * been, so the analyst knows how far to narrow.
 */
export interface BatchRefusal {
  code: Code;
  cap_kind?: CapKind;
  cap?: Cap;
  would_be?: WouldBe;
}
