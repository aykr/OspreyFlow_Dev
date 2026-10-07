// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type Id = string;
export type Identifier = string;
export type OwnerId = string;
export type ReviewDate = string;
export type Status = "active" | "stopped";
export type CreatedAt = string;
export type DatasetId = string | null;

/**
 * A watched identifier — `02_GLASS_FRONTEND.md` §3.3: "A list of identifiers with an owner
 * and a review date." Phase 7 Stage 6b/6c. Deliberately bare: an `identifier` is a normalised
 * value string (the same `value_normalised` shape `Endpoint`'s own identifiers already use, not
 * a node id — a hotlist entry can be created before anything resolves to a node at all, per
 * ADR-038's own "an analyst can hotlist a bare phone number read off a warrant before it
 * resolves to anything they can see"), an `owner_id`, and a `review_date` — no handling ceiling
 * (`06_DECISIONS.md` ADR-038's option (c), recorded there as not selected, not built here).
 *
 * `status` (Stage 6c): `06_DECISIONS.md` ADR-036's own "the monitor stops" requirement, extended
 * here — see `WatchStatus`'s own docstring. The investigation a jumped-to alert branches into
 * comes from `Alert.investigation_id` (the *triggering* event's own investigation, threaded
 * through `ChangeStreamEntry`), not from this row — a hotlist is not investigation-scoped and
 * outlives any one investigation it happened to be set from.
 */
export interface Hotlist {
  id: Id;
  identifier: Identifier;
  owner_id: OwnerId;
  review_date: ReviewDate;
  status?: Status;
  created_at: CreatedAt;
  dataset_id?: DatasetId;
  [k: string]: unknown;
}
