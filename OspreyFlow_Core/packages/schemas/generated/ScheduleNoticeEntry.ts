// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type NoticeId = string;
export type RecipeId = string;
export type RaisedAt = string;
export type Words = string;

/**
 * One scheduled load's notice in its owner's *Needs you* (ADR-110 Amendment 19): a run of their
 * schedule that failed or was refused, in its own words. Only ever its owner's (the read is
 * filtered by owner in the query); it names the recipe, never another person.
 */
export interface ScheduleNoticeEntry {
  notice_id: NoticeId;
  recipe_id: RecipeId;
  raised_at: RaisedAt;
  words: Words;
  [k: string]: unknown;
}
