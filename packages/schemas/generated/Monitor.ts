// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type PatternId = string;
export type OwnerId = string;
export type CreatedAt = string;

/**
 * A saved pattern being watched — `02_GLASS_FRONTEND.md` §3.3: "A saved visual query run...
 * against new data." Phase 7 Stage 6b. References a `SavedPattern` by `pattern_id`, never
 * copies its own definition — `PatternStore.get_authorized` is the one place a monitor's own
 * query is ever read from, the same "resolved fresh, never cached" discipline `06_DECISIONS.md`
 * ADR-036 requires of a monitor's *access*, extended here to its own *definition* too, so an
 * edited-then-resaved pattern is evaluated as it now reads, not as it read when the monitor was
 * turned on. `owner_id` is redundant with `SavedPattern.owner_id` (a monitor cannot be turned on
 * for a pattern its own creator does not own — checked at creation, not re-derived from the
 * pattern on every read) but stored directly so a monitor row is self-describing without a join
 * for the common "list my own monitors" case.
 */
export interface Monitor {
  id: Id;
  pattern_id: PatternId;
  owner_id: OwnerId;
  created_at: CreatedAt;
  [k: string]: unknown;
}
